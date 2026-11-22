import SwiftUI

private enum RecipeMode: String, CaseIterable, Identifiable { case library, today, explore; var id: String { rawValue }; var title: String { switch self { case .library: "菜谱库"; case .today: "今日推荐"; case .explore: "探索" } } }
private enum RecipeSheet: Identifiable { case add, edit(Recipe), cook(Recipe); var id: String { switch self { case .add: "add"; case .edit(let r): "edit-\(r.id)"; case .cook(let r): "cook-\(r.id)" } } }
private enum RecipeDetailPresentation: Identifiable {
    case edit(Recipe), cook(Recipe), confirmDelete(Recipe)
    var id: String { switch self { case .edit(let recipe): "edit-\(recipe.id)"; case .cook(let recipe): "cook-\(recipe.id)"; case .confirmDelete(let recipe): "delete-\(recipe.id)" } }
    var isSheet: Bool { if case .confirmDelete = self { false } else { true } }
}

struct RecipeLibraryView: View {
    @Environment(RecipeStore.self) private var recipes
    @Environment(CapabilitiesStore.self) private var capabilities
    @State private var mode: RecipeMode = .library
    @State private var sheet: RecipeSheet?
    var body: some View {
        VStack(spacing: 0) {
            Picker("模式", selection: $mode) { ForEach(RecipeMode.allCases) { Text($0.title).tag($0) } }.pickerStyle(.segmented).padding()
            switch mode {
            case .library: library
            case .today: RecommendationView()
            case .explore: ExploreView(client: recipes.client, capabilities: capabilities)
            }
        }
        .navigationTitle("菜谱")
        .toolbar { if mode == .library { Button { sheet = .add } label: { Image(systemName: "plus") } } }
        .sheet(item: $sheet) { value in NavigationStack { switch value { case .add: RecipeEditorView(recipe: nil, draft: nil); case .edit(let recipe): RecipeEditorView(recipe: recipe, draft: nil); case .cook(let recipe): CookRecipeView(recipe: recipe) } } }
    }

    private var library: some View {
        @Bindable var store = recipes
        return Group {
            switch store.state {
            case .idle where store.recipes.isEmpty, .loading where store.recipes.isEmpty: LoadingView()
            case .failed(let message) where store.recipes.isEmpty: FailureView(message: message) { Task { await store.load() } }
            default:
                if store.recipes.isEmpty { EmptyStateView(title: "没有找到菜谱", message: "调整搜索或筛选条件。", icon: "fork.knife") }
                else { List { ForEach(store.recipes) { recipe in NavigationLink { RecipeDetailView(recipeID: recipe.id) } label: { RecipeSummaryRow(recipe: recipe) }.onAppear { if recipe.id == store.recipes.last?.id && store.canLoadMore { Task { await store.load(reset: false) } } } }; if store.pagination == .loading { HStack { Spacer(); ProgressView(); Spacer() } } } }
            }
        }
        .searchable(text: $store.query, prompt: "搜索菜谱")
        .task(id: store.query) { try? await Task.sleep(for: .milliseconds(300)); guard !Task.isCancelled else { return }; await store.load() }
        .refreshableWithCapabilities { await store.load() }
        .safeAreaInset(edge: .bottom) { RecipeFilterBar() }
    }
}

private struct RecipeFilterBar: View {
    @Environment(RecipeStore.self) private var recipes
    var body: some View {
        @Bindable var store = recipes
        ScrollView(.horizontal, showsIndicators: false) {
            HStack {
                Menu { Button("全部来源") { store.source = nil }; ForEach(RecipeSourceFilter.allCases) { value in Button(value.title) { store.source = value } } } label: { Label(store.source?.title ?? "全部来源", systemImage: "tray.full") }
                Menu { Button("全部分类") { store.category = nil }; ForEach(RecipeCategory.allCases) { value in Button(value.title) { store.category = value } } } label: { Label(store.category?.title ?? "全部分类", systemImage: "square.grid.2x2") }
                Toggle(isOn: $store.favoritesOnly) { Label("仅收藏", systemImage: "heart") }.toggleStyle(.button)
            }.padding(.horizontal).padding(.vertical, 8)
        }.background(.bar).onChange(of: store.source) { Task { await store.load() } }.onChange(of: store.category) { Task { await store.load() } }.onChange(of: store.favoritesOnly) { Task { await store.load() } }
    }
}

private struct RecipeSummaryRow: View {
    let recipe: RecipeSummary
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack { Text(recipe.title).font(.headline); Spacer(); if recipe.isFavorite { Image(systemName: "heart.fill").foregroundStyle(.red) } }
            HStack { if let category = recipe.category { Text(RecipeCategory(rawValue: category)?.title ?? category) }; if let time = recipe.cookTimeMinutes { Label("\(time) 分钟", systemImage: "clock") }; if recipe.hasBeenCooked { Label("做过", systemImage: "checkmark.circle") } }.font(.caption).foregroundStyle(.secondary)
            Text(recipe.isUserCreated ? "我的菜谱" : recipe.sourceName).font(.caption2).foregroundStyle(.tertiary)
        }.padding(.vertical, 4)
    }
}

private struct RecommendationView: View {
    @Environment(RecipeStore.self) private var store
    @State private var scene: RecommendationScene = .all
    @State private var state: LoadState<RecommendationSnapshot> = .idle
    var body: some View {
        VStack {
            Picker("场景", selection: $scene) { ForEach(RecommendationScene.allCases) { Text($0.title).tag($0) } }.pickerStyle(.segmented).padding(.horizontal)
            switch state {
            case .idle, .loading: LoadingView()
            case .failed(let message): FailureView(message: message) { Task { await load() } }
            case .loaded(let snapshot):
                if snapshot.recommendations.isEmpty { EmptyStateView(title: "暂无推荐", message: snapshot.emptyMessage, icon: "sparkles") }
                else { List(snapshot.recommendations) { item in NavigationLink { RecipeDetailView(recipeID: item.recipeId) } label: { VStack(alignment: .leading, spacing: 7) { Text(item.title).font(.headline); if let reason = item.reason { Text(reason).font(.subheadline).foregroundStyle(.secondary) }; HStack { Label("匹配 \(item.matchedInventoryItems.count)", systemImage: "checkmark.circle"); if !item.expiringInventoryItems.isEmpty { Label("优先消耗", systemImage: "clock").foregroundStyle(.orange) }; Spacer(); Text(item.score.formatted()) }.font(.caption) } } } }
            }
        }.task(id: scene) { await load() }.refreshableWithCapabilities { await load() }
    }
    private func load() async { state = .loading; do { state = .loaded(try await store.recommendations(scene: scene)) } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) } }
}

struct RecipeDetailView: View {
    let recipeID: Int
    @Environment(\.dismiss) private var dismiss
    @Environment(RecipeStore.self) private var store
    @State private var state: LoadState<Recipe> = .idle
    @State private var presentation: RecipeDetailPresentation?
    @State private var action: ActionState = .idle
    var body: some View {
        Group {
            switch state {
            case .loaded(let recipe):
                List {
                    Section { VStack(alignment: .leading, spacing: 10) { Text(recipe.title).font(.largeTitle.bold()); if let description = recipe.description { Text(description).foregroundStyle(.secondary) }; HStack { if let value = recipe.difficulty { Label(DisplayText.difficulty(value), systemImage: "gauge") }; if let value = recipe.servings { Label(value, systemImage: "person.2") }; if let value = recipe.cookTimeMinutes { Label("\(value) 分钟", systemImage: "clock") } }.font(.subheadline) } }
                    Section("食材") { ForEach(recipe.ingredients) { ingredient in HStack { Text(ingredient.ingredientName); if ingredient.isOptional { Text("可选").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text([ingredient.quantity, ingredient.unit].compactMap { $0 }.joined()).foregroundStyle(.secondary) } } }
                    Section("步骤") { ForEach(recipe.steps.sorted { $0.stepNumber < $1.stepNumber }) { step in HStack(alignment: .top) { Text("\(step.stepNumber)").font(.headline).frame(width: 28, height: 28).background(.tint.opacity(0.15), in: Circle()); Text(step.instruction) } } }
                    Section("来源") { LabeledValue(label: "来源", value: recipe.sourceName); if let license = recipe.licenseName { LabeledValue(label: "许可", value: license) }; if let text = recipe.sourceUrl, let url = URL(string: text) { Link("查看原始来源", destination: url) } }
                    Section { Button("开始烹饪", systemImage: "flame.fill") { presentation = .cook(recipe) }.buttonStyle(.borderedProminent); if recipe.isUserCreated { Button("编辑菜谱", systemImage: "pencil") { presentation = .edit(recipe) }; Button("删除菜谱", systemImage: "trash", role: .destructive) { presentation = .confirmDelete(recipe) } } else { Button("复刻为我的菜谱", systemImage: "doc.on.doc") { Task { await fork() } } } }
                }
            case .idle, .loading: LoadingView()
            case .failed(let message): FailureView(message: message) { Task { await load() } }
            }
        }
        .navigationTitle("菜谱详情").navigationBarTitleDisplayMode(.inline)
        .toolbar { if let recipe = loadedRecipe { Button { Task { await favorite(!recipe.isFavorite) } } label: { Image(systemName: recipe.isFavorite ? "heart.fill" : "heart") } } }
        .task { await load() }
        .sheet(item: sheetPresentation, onDismiss: { Task { await load() } }) { value in NavigationStack { switch value { case .edit(let recipe): RecipeEditorView(recipe: recipe, draft: nil); case .cook(let recipe): CookRecipeView(recipe: recipe); case .confirmDelete: EmptyView() } } }
        .confirmationDialog("删除“\(loadedRecipe?.title ?? "")”？", isPresented: deleteConfirmation) { Button("永久删除", role: .destructive) { Task { await delete() } } } message: { Text("收藏与烹饪历史也会删除，操作无法撤销。") }
        .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var loadedRecipe: Recipe? { if case .loaded(let recipe) = state { recipe } else { nil } }
    private var sheetPresentation: Binding<RecipeDetailPresentation?> { Binding(get: { presentation?.isSheet == true ? presentation : nil }, set: { presentation = $0 }) }
    private var deleteConfirmation: Binding<Bool> { Binding(get: { if case .confirmDelete = presentation { true } else { false } }, set: { if !$0 { presentation = nil } }) }
    private func load() async { state = .loading; do { state = .loaded(try await store.client.recipe(id: recipeID)) } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) } }
    private func favorite(_ value: Bool) async { action = .running; do { try await store.client.setFavorite(id: recipeID, favorite: value); await load(); action = .succeeded(nil) } catch { action = .failed(error.localizedDescription) } }
    private func fork() async { action = .running; do { let copy = try await store.client.forkRecipe(id: recipeID); state = .loaded(copy); await store.load(); action = .succeeded(nil) } catch { action = .failed(error.localizedDescription) } }
    private func delete() async { action = .running; do { try await store.delete(id: recipeID); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}

struct RecipeEditorView: View {
    let recipe: Recipe?
    private let warnings: [AIWarning]
    private let legacyDifficulty: String?
    @Environment(\.dismiss) private var dismiss
    @Environment(RecipeStore.self) private var store
    @State private var draft: RecipeDraft
    @State private var action: ActionState = .idle
    init(recipe: Recipe?, draft: RecipeDraft?, warnings: [AIWarning] = []) {
        self.recipe = recipe
        self.warnings = warnings
        let value = draft ?? RecipeDraft(title: recipe?.title ?? "", category: recipe?.category.flatMap(RecipeCategory.init(rawValue:)), description: recipe?.description, difficulty: recipe?.difficulty, servings: recipe?.servings, cookTimeMinutes: recipe?.cookTimeMinutes, rawMarkdown: recipe?.rawMarkdown, ingredients: recipe?.ingredients ?? [], steps: recipe?.steps ?? [])
        legacyDifficulty = value.difficulty.flatMap { DisplayText.recipeDifficulties.contains($0) ? nil : $0 }
        _draft = State(initialValue: value)
    }
    var body: some View {
        Form {
            if !warnings.isEmpty {
                Section("AI 草稿提示") {
                    ExploreWarnings(warnings: warnings)
                }
            }
            Section("基本信息") {
                TextField("标题", text: $draft.title)
                Picker("分类", selection: $draft.category) {
                    Text("请选择").tag(RecipeCategory?.none)
                    ForEach(RecipeCategory.allCases) { Text($0.title).tag(Optional($0)) }
                }
                TextField("简介", text: optional($draft.description), axis: .vertical)
                Picker("难度", selection: $draft.difficulty) {
                    Text("未设置").tag(String?.none)
                    ForEach(DisplayText.recipeDifficulties, id: \.self) {
                        Text(DisplayText.difficulty($0)).tag(Optional($0))
                    }
                    if let legacyDifficulty {
                        Text("当前：\(legacyDifficulty)").tag(Optional(legacyDifficulty))
                    }
                }
                TextField("份量", text: optional($draft.servings))
                TextField("烹饪分钟", value: $draft.cookTimeMinutes, format: .number).keyboardType(.numberPad)
            }
            Section("食材") {
                ForEach($draft.ingredients) { $ingredient in
                    VStack(alignment: .leading) {
                        HStack {
                            TextField("食材名称", text: $ingredient.ingredientName)
                            Menu {
                                Toggle("可选", isOn: $ingredient.isOptional)
                                Toggle("调味料", isOn: $ingredient.isSeasoning)
                            } label: {
                                Image(systemName: "ellipsis.circle").accessibilityLabel("食材选项")
                            }
                        }
                        HStack {
                            TextField("数量", text: optional($ingredient.quantity))
                            TextField("单位", text: optional($ingredient.unit))
                        }
                        if ingredient.isOptional || ingredient.isSeasoning {
                            HStack {
                                if ingredient.isOptional { Text("可选") }
                                if ingredient.isSeasoning { Text("调味料") }
                            }
                            .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .swipeActions {
                        Button("删除", role: .destructive) {
                            draft.ingredients.removeAll { $0.id == ingredient.id }
                        }
                    }
                }
                Button("添加食材", systemImage: "plus") {
                    draft.ingredients.append(.init(ingredientName: "", sortOrder: draft.ingredients.count))
                }
            }
            Section("步骤") { ForEach($draft.steps) { $step in TextField("步骤 \(step.stepNumber)", text: $step.instruction, axis: .vertical).swipeActions { Button("删除", role: .destructive) { draft.steps.removeAll { $0.id == step.id }; renumber() } } }; Button("添加步骤", systemImage: "plus") { draft.steps.append(.init(stepNumber: draft.steps.count + 1, instruction: "")) } }
        }.navigationTitle(recipe == nil ? "新建菜谱" : "编辑菜谱").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("保存") { Task { await save() } }.disabled(!valid || action.isRunning) } }
            .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var valid: Bool { !draft.title.trimmed.isEmpty && draft.category != nil && !draft.ingredients.isEmpty && draft.ingredients.allSatisfy { !$0.ingredientName.trimmed.isEmpty } && !draft.steps.isEmpty && draft.steps.allSatisfy { !$0.instruction.trimmed.isEmpty } }
    private func optional(_ binding: Binding<String?>) -> Binding<String> { Binding(get: { binding.wrappedValue ?? "" }, set: { binding.wrappedValue = $0.nilIfBlank }) }
    private func renumber() { for index in draft.steps.indices { draft.steps[index].stepNumber = index + 1 } }
    private func save() async {
        guard let category = draft.category else { return }; action = .running
        let body = RecipeWrite(title: draft.title.trimmed, category: category, description: draft.description, difficulty: draft.difficulty, servings: draft.servings, cookTimeMinutes: draft.cookTimeMinutes, rawMarkdown: draft.rawMarkdown, ingredients: draft.ingredients, steps: draft.steps)
        do { if let recipe { _ = try await store.client.updateRecipe(id: recipe.id, body) } else { _ = try await store.client.createRecipe(body) }; await store.load(); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) }
    }
}

private struct CookRecipeView: View {
    let recipe: Recipe
    @Environment(\.dismiss) private var dismiss
    @Environment(RecipeStore.self) private var store
    @State private var previewState: LoadState<ConsumePreview> = .idle
    @State private var selected: Set<Int> = []
    @State private var amounts: [Int: String] = [:]
    @State private var notes = ""; @State private var action: ActionState = .idle
    var body: some View {
        Group {
            switch previewState {
            case .idle, .loading: LoadingView(text: "正在匹配库存…")
            case .loaded(let preview):
                Form {
                    Section("将要扣减的库存") {
                        ForEach(preview.suggestions) { item in
                            CookSuggestionRow(item: item, isSelected: selectionBinding(item.itemId), amount: amountBinding(item.itemId))
                        }
                    }
                    if !preview.unmatchedIngredients.isEmpty { Section("未匹配食材") { ForEach(preview.unmatchedIngredients, id: \.self) { Text($0) } } }
                    Section("烹饪备注") { TextEditor(text: $notes).frame(minHeight: 70) }
                }
            case .failed(let message): FailureView(message: message) { Task { await load() } }
            }
        }.navigationTitle("烹饪 \(recipe.title)").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("完成烹饪") { Task { await cook() } }.disabled(consumption == nil || action.isRunning) } }
            .task { await load() }.savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var consumption: [CookConsumeItem]? {
        guard case .loaded(let preview) = previewState else { return nil }
        return preview.consumption(selected: selected, amounts: amounts)
    }
    private func selectionBinding(_ id: Int) -> Binding<Bool> {
        Binding(get: { selected.contains(id) }, set: { value in if value { selected.insert(id) } else { selected.remove(id) } })
    }
    private func amountBinding(_ id: Int) -> Binding<String> {
        Binding(get: { amounts[id] ?? "" }, set: { amounts[id] = $0 })
    }
    private func load() async { previewState = .loading; do { let value = try await store.client.consumePreview(recipeId: recipe.id); selected.removeAll(); amounts.removeAll(); for item in value.suggestions { if let q = item.suggestedQuantity { selected.insert(item.itemId); amounts[item.itemId] = q.formatted() } }; previewState = .loaded(value) } catch is CancellationError { return } catch { previewState = .failed(error.localizedDescription) } }
    private func cook() async {
        guard let consumption else { return }
        action = .running
        do {
            _ = try await store.client.cook(recipeId: recipe.id, .init(consumeItems: consumption, notes: notes.nilIfBlank))
            await store.load()
            action = .succeeded(nil)
            dismiss()
        } catch {
            action = .failed(error.localizedDescription)
        }
    }
}

private struct CookSuggestionRow: View {
    let item: ConsumePreviewItem
    @Binding var isSelected: Bool
    @Binding var amount: String
    var body: some View {
        Toggle(isOn: $isSelected) {
            VStack(alignment: .leading, spacing: 4) {
                Text("\(item.ingredientName) → \(item.itemName)")
                Text("库存 \(item.availableQuantity.formatted()) \(item.unit) · 菜谱 \(item.recipeQuantity ?? "未注明")")
                    .font(.caption).foregroundStyle(.secondary)
                TextField("扣减数量（\(item.unit)）", text: $amount).keyboardType(.decimalPad)
            }
        }
    }
}
