import SwiftUI

private struct SettingsSnapshot {
    let settings: AppSettings
    let sources: [SourceInfo]
}

private enum SettingsPresentation: Identifiable, Equatable {
    case connection
    case confirmDisconnect

    var id: String { switch self { case .connection: "connection"; case .confirmDisconnect: "disconnect" } }
}

struct SettingsView: View {
    @Environment(AppSession.self) private var session
    @Environment(InventoryStore.self) private var inventory
    @State private var state: LoadState<SettingsSnapshot> = .idle
    @State private var days = 2
    @State private var presentation: SettingsPresentation?
    @State private var action: ActionState = .idle
    var body: some View {
        Form {
            Section("服务器") {
                LabeledValue(label: "地址", value: session.configuredURL)
                LabeledValue(label: "状态", value: session.isConnected ? "已连接" : "未连接")
                if let health = session.health { LabeledValue(label: "后端版本", value: health.version) }
                Button("测试或修改连接", systemImage: "network") { presentation = .connection }
                Button("移除本机令牌", systemImage: "key.slash", role: .destructive) { presentation = .confirmDisconnect }
            }
            Section("过期提醒") {
                Stepper("提前 \(days) 天提醒", value: $days, in: 0...365)
                Button("保存提醒设置") { Task { await saveDays() } }.disabled(action.isRunning || loadedSettings?.expirationReminderDays == String(days))
            }
            Section("库存结构") { NavigationLink { CategoryManagementView() } label: { Label("分类管理", systemImage: "folder") } }
            if !loadedSources.isEmpty {
                Section("菜谱来源") { ForEach(loadedSources) { source in VStack(alignment: .leading, spacing: 5) { Text(source.name).font(.headline); Text(source.license).font(.caption).foregroundStyle(.secondary); Text(source.notice).font(.footnote).foregroundStyle(.secondary); if let url = URL(string: source.url) { Link("查看来源", destination: url) } } } }
            }
            if case .failed(let message) = state { Section { FailureView(message: message) { Task { await load() } } } }
            Section("关于") { Text("Stock Manager 是连接家庭自托管后端的原生客户端。令牌仅保存在本机 Keychain。") }
        }
        .navigationTitle("设置").task { await load() }
        .sheet(item: connectionPresentation) { _ in ConnectionSettingsView() }
        .confirmationDialog("移除令牌并断开连接？", isPresented: disconnectConfirmation) {
            Button("移除并断开", role: .destructive) { disconnect() }
        } message: { Text("服务器数据不会删除；下次启动需要重新输入 API 令牌。") }
        .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var loadedSettings: AppSettings? { if case .loaded(let snapshot) = state { snapshot.settings } else { nil } }
    private var loadedSources: [SourceInfo] { if case .loaded(let snapshot) = state { snapshot.sources } else { [] } }
    private var connectionPresentation: Binding<SettingsPresentation?> { Binding(get: { presentation == .connection ? presentation : nil }, set: { presentation = $0 }) }
    private var disconnectConfirmation: Binding<Bool> { Binding(get: { presentation == .confirmDisconnect }, set: { if !$0 { presentation = nil } }) }
    private func load() async { state = .loading; do { async let a = inventory.client.settings(); async let b = inventory.client.recipeSources(); let (loaded, sourceList) = try await (a, b); days = Int(loaded.expirationReminderDays) ?? 2; state = .loaded(.init(settings: loaded, sources: sourceList)) } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) } }
    private func saveDays() async { action = .running; do { let updated = try await inventory.client.updateSettings(days: days); state = .loaded(.init(settings: updated, sources: loadedSources)); action = .succeeded(nil) } catch { action = .failed(error.localizedDescription) } }
    private func disconnect() { do { try session.disconnect(); presentation = nil } catch { action = .failed(error.localizedDescription) } }
}

private struct ConnectionSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppSession.self) private var session
    @State private var url = ""; @State private var token = ""; @State private var action: ActionState = .idle
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("服务器地址", text: $url).textInputAutocapitalization(.never).keyboardType(.URL)
                    SecureField("输入新的 API 令牌", text: $token).privacySensitive()
                } header: { Text("连接") } footer: { Text("出于安全原因，现有令牌不会显示。保存时必须重新输入。") }
            }
                .navigationTitle("服务器连接").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("测试并保存") { Task { await save() } }.disabled(url.trimmed.isEmpty || token.trimmed.isEmpty || action.isRunning) } }
                .onAppear { url = session.configuredURL }.savingOverlay(action.isRunning).actionErrorAlert($action)
        }
    }
    private func save() async { action = .running; do { try await session.connect(urlText: url, token: token); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}

private enum CategoryPresentation: Identifiable { case add(parent: Int?), edit(Category), confirmDelete(Category); var id: String { switch self { case .add(let id): "add-\(id ?? 0)"; case .edit(let c): "edit-\(c.id)"; case .confirmDelete(let c): "delete-\(c.id)" } }; var isSheet: Bool { if case .confirmDelete = self { false } else { true } } }

struct CategoryManagementView: View {
    @Environment(CategoryStore.self) private var categories
    @State private var presentation: CategoryPresentation?
    @State private var action: ActionState = .idle
    var body: some View {
        Group {
            switch categories.state {
            case .idle where categories.tree.isEmpty, .loading where categories.tree.isEmpty:
                LoadingView()
            case .failed(let message) where categories.tree.isEmpty:
                FailureView(message: message) { Task { await categories.load() } }
            default:
                List {
                    ForEach(categories.tree) { parent in
                        Section {
                            categoryRow(parent)
                            ForEach(parent.children ?? []) { child in
                                categoryRow(child).padding(.leading, 16)
                            }
                        } header: {
                            HStack {
                                Text(parent.name)
                                Spacer()
                                Button { presentation = .add(parent: parent.id) } label: { Image(systemName: "plus.circle") }
                                    .accessibilityLabel("在 \(parent.name) 下添加子分类")
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("分类管理")
        .toolbar { Button { presentation = .add(parent: nil) } label: { Image(systemName: "plus") } }
        .task { await categories.load() }
        .refreshableWithCapabilities { await categories.load() }
            .sheet(item: sheetPresentation) { value in NavigationStack { switch value { case .add(let parent): CategoryEditorView(category: nil, initialParent: parent); case .edit(let category): CategoryEditorView(category: category, initialParent: category.parentId); case .confirmDelete: EmptyView() } } }
            .confirmationDialog("删除分类“\(deletingCategory?.name ?? "")”？", isPresented: deleteConfirmation) {
                Button("永久删除", role: .destructive) { if let value = deletingCategory { Task { await delete(value) } } }
            } message: { Text("有子分类或仍被库存使用时，服务器会拒绝删除。系统分类不能删除。") }.savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private func categoryRow(_ category: Category) -> some View {
        HStack { VStack(alignment: .leading) { Text(category.name); Text(category.recipeUsage.title).font(.caption).foregroundStyle(.secondary) }; Spacer(); if category.isSystem { Label("系统", systemImage: "lock").font(.caption).foregroundStyle(.secondary) } }
            .contentShape(Rectangle()).onTapGesture { presentation = .edit(category) }.swipeActions { if !category.isSystem { Button("删除", role: .destructive) { presentation = .confirmDelete(category) }; Button("编辑") { presentation = .edit(category) }.tint(.blue) } }
    }
    private var sheetPresentation: Binding<CategoryPresentation?> { Binding(get: { presentation?.isSheet == true ? presentation : nil }, set: { presentation = $0 }) }
    private var deletingCategory: Category? { if case .confirmDelete(let category) = presentation { category } else { nil } }
    private var deleteConfirmation: Binding<Bool> { Binding(get: { deletingCategory != nil }, set: { if !$0 { presentation = nil } }) }
    private func delete(_ category: Category) async { action = .running; do { try await categories.delete(category); presentation = nil; action = .succeeded(nil) } catch { action = .failed(error.localizedDescription) } }
}

private struct CategoryEditorView: View {
    let category: Category?
    @Environment(\.dismiss) private var dismiss
    @Environment(CategoryStore.self) private var store
    @State private var name: String; @State private var parent: Int?; @State private var usage: RecipeUsage; @State private var order: Int
    @State private var action: ActionState = .idle
    init(category: Category?, initialParent: Int?) { self.category = category; _name = State(initialValue: category?.name ?? ""); _parent = State(initialValue: initialParent); _usage = State(initialValue: category?.recipeUsage ?? .always); _order = State(initialValue: category?.sortOrder ?? 0) }
    var body: some View {
        Form {
            Section("分类") { TextField("名称", text: $name).disabled(category?.isSystem == true); Picker("父分类", selection: $parent) { Text("顶级分类").tag(Int?.none); ForEach(store.flat.filter { $0.parentId == nil && $0.id != category?.id }) { Text($0.name).tag(Optional($0.id)) } }.disabled(category?.isSystem == true); Picker("菜谱用途", selection: $usage) { ForEach(RecipeUsage.allCases) { Text($0.title).tag($0) } }; Stepper("排序：\(order)", value: $order, in: -1000...1000) }
            if category?.isSystem == true { Section { Text("系统分类的名称和层级由后端保护；可以调整菜谱用途和显示顺序。") }.font(.footnote).foregroundStyle(.secondary) }
        }.navigationTitle(category == nil ? "新增分类" : "编辑分类").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("保存") { Task { await save() } }.disabled(name.trimmed.isEmpty || action.isRunning) } }.savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private func save() async { action = .running; do { if let category { try await store.update(category, name: name, parent: parent, usage: usage, order: order) } else { try await store.create(name: name, parent: parent, usage: usage, order: order) }; action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}
