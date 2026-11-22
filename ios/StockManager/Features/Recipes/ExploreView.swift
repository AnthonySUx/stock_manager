import SwiftUI

private enum ExploreInputMode: String, CaseIterable, Identifiable {
    case naturalLanguage = "natural_language"
    case structured
    var id: String { rawValue }
    var title: String { self == .naturalLanguage ? "自然语言" : "结构化条件" }
}

struct ExploreView: View {
    @Environment(InventoryStore.self) private var inventory
    @State private var store: ExploreStore
    @State private var inputMode: ExploreInputMode = .naturalLanguage
    @State private var prompt = ""
    @FocusState private var promptFocused: Bool
    @State private var selectedInventory: Set<Int> = []
    @State private var flavors = ""
    @State private var methods = ""
    @State private var maxMinutes: Int?
    @State private var expandedDraft: IdentifiedDraft?
    @State private var operationTask: Task<Void, Never>?

    init(client: any APIClientProtocol, capabilities: CapabilitiesStore) {
        _store = State(initialValue: ExploreStore(client: client, capabilities: capabilities))
    }

    var body: some View {
        Form {
            Section {
                Picker("输入方式", selection: $inputMode) {
                    ForEach(ExploreInputMode.allCases) { Text($0.title).tag($0) }
                }.pickerStyle(.segmented)
            }
            if inputMode == .naturalLanguage {
                Section("告诉我想吃什么") {
                    TextField("例如：想做清淡、30 分钟内的晚餐", text: $prompt, axis: .vertical)
                        .lineLimit(3...6)
                        .focused($promptFocused)
                        .accessibilityIdentifier("explore.prompt")
                }
            } else {
                preferencesSection
                inventorySection
            }
            Section {
                if store.state.isGenerating {
                    HStack {
                        ProgressView()
                        Text("正在生成创意")
                        Spacer()
                        Button("停止") { operationTask?.cancel() }
                            .accessibilityIdentifier("explore.stop")
                    }
                } else {
                    Button {
                        promptFocused = false
                        start(.generate(request))
                    } label: {
                        Label("生成创意", systemImage: "sparkles").frame(maxWidth: .infinity)
                    }
                    .disabled(!store.isAvailable || store.state.isLoading || (inputMode == .naturalLanguage && prompt.trimmed.isEmpty))
                    .accessibilityIdentifier("explore.generate")
                }
                if !store.isAvailable {
                    Label(DisplayText.aiUnavailable, systemImage: "sparkles")
                        .foregroundStyle(.secondary)
                }
            }
            if case .failed(_, let message, let retry) = store.state {
                Section {
                    Label(message, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    if let retry {
                        Button("重试") { start(retry) }.disabled(!store.isAvailable)
                    }
                }
            }
            if let results = store.state.results {
                if !store.state.isGenerating, !results.warnings.isEmpty {
                    Section { ExploreWarnings(warnings: results.warnings) }
                }
                if !results.ideas.isEmpty {
                    Section("创意结果") {
                        ForEach(results.ideas) { idea in
                            ideaRow(idea)
                        }
                    }
                } else if case .loaded = store.state, results.warnings.isEmpty {
                    Section {
                        ContentUnavailableView("没有生成创意", systemImage: "sparkles",
                                               description: Text("请换一种描述后重试。"))
                    }
                }
            }
        }
        .task { if inventory.items.isEmpty { await inventory.load() } }
        .onDisappear { operationTask?.cancel() }
        .refreshableWithCapabilities { await inventory.load() }
        .sheet(item: $expandedDraft) { draft in
            NavigationStack {
                RecipeEditorView(recipe: nil, draft: draft.response.recipeDraft, warnings: draft.response.warnings)
            }
        }
    }

    @ViewBuilder private func ideaRow(_ idea: ExploreIdea) -> some View {
        switch idea.action {
        case .openRecipe(let id):
            NavigationLink {
                RecipeDetailView(recipeID: id)
            } label: {
                VStack(alignment: .leading, spacing: 8) {
                    ExploreIdeaSummary(idea: idea)
                    Label("菜谱库已有", systemImage: "book").font(.caption.weight(.semibold))
                }
            }
        case .expand:
            VStack(alignment: .leading, spacing: 8) {
                ExploreIdeaSummary(idea: idea)
                Button("展开为菜谱草稿") { start(.expand(idea)) }
                    .disabled(store.state.isLoading || !store.isAvailable)
            }
        case .none:
            ExploreIdeaSummary(idea: idea)
        }
    }

    private var preferencesSection: some View {
        Section("偏好") {
            TextField("口味（逗号分隔）", text: $flavors)
            TextField("做法（逗号分隔）", text: $methods)
            TextField("最多分钟", value: $maxMinutes, format: .number).keyboardType(.numberPad)
        }
    }

    private var inventorySection: some View {
        Section("选择库存（不选表示全部）") {
            ForEach(inventory.items.filter { [.active, .expiringSoon].contains($0.status) && $0.category.recipeUsage != .never }) { item in
                Toggle("\(item.name) · \(item.quantityText)", isOn: inventoryBinding(item.id))
            }
        }
    }

    private var request: ExploreRequest {
        switch inputMode {
        case .naturalLanguage:
            return .init(mode: inputMode.rawValue, structured: nil, naturalLanguage: prompt.trimmed)
        case .structured:
            let preferences = ExplorePreferences(inventoryItemIds: selectedInventory.sorted(),
                                                 flavors: parts(flavors), cookingMethods: parts(methods), maxTimeMinutes: maxMinutes)
            return .init(mode: inputMode.rawValue, structured: preferences, naturalLanguage: nil)
        }
    }

    private func inventoryBinding(_ id: Int) -> Binding<Bool> {
        Binding(get: { selectedInventory.contains(id) }, set: { value in
            if value { selectedInventory.insert(id) } else { selectedInventory.remove(id) }
        })
    }

    private func parts(_ text: String) -> [String] {
        text.split(separator: ",").map { String($0).trimmed }.filter { !$0.isEmpty }
    }

    private func start(_ operation: ExploreOperation) {
        guard operationTask == nil else { return }
        operationTask = Task {
            defer { operationTask = nil }
            if let response = await store.perform(operation), !Task.isCancelled {
                expandedDraft = IdentifiedDraft(response: response)
            }
        }
    }
}

private struct ExploreIdeaSummary: View {
    let idea: ExploreIdea

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(idea.title).font(.headline)
            if let description = idea.description { Text(description).foregroundStyle(.secondary) }
            if let reason = idea.reason { Text(reason).font(.caption).foregroundStyle(.secondary) }
            let metadata = [
                idea.cookingMethod.map(DisplayText.cookingMethod),
                idea.cuisine ?? idea.cuisineGroup.map(DisplayText.cuisineGroup),
                idea.estimatedTimeMinutes.map { "\($0) 分钟" }
            ].compactMap { $0 }
            if !metadata.isEmpty {
                Text(metadata.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

struct ExploreWarnings: View {
    let warnings: [AIWarning]

    var body: some View {
        ForEach(Array(warnings.enumerated()), id: \.offset) { _, warning in
            Label(DisplayText.aiWarning(warning), systemImage: "exclamationmark.triangle")
                .foregroundStyle(.secondary)
        }
    }
}

private struct IdentifiedDraft: Identifiable {
    let id = UUID()
    let response: ExpandResponse
}
