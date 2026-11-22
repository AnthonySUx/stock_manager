import SwiftUI

private enum RestockPresentation: Identifiable {
    case add, edit(RestockItem), complete(RestockItem), confirmDelete(RestockItem), confirmClean
    var id: String { switch self { case .add: "add"; case .edit(let i): "edit-\(i.id)"; case .complete(let i): "complete-\(i.id)"; case .confirmDelete(let i): "delete-\(i.id)"; case .confirmClean: "clean" } }
    var isSheet: Bool { switch self { case .add, .edit, .complete: true; case .confirmDelete, .confirmClean: false } }
}

struct RestockListView: View {
    @Environment(RestockStore.self) private var restock
    @Environment(CategoryStore.self) private var categories
    @State private var presentation: RestockPresentation?
    @State private var action: ActionState = .idle
    var body: some View {
        @Bindable var store = restock
        VStack(spacing: 0) {
            Picker("状态", selection: $store.selection) { ForEach(RestockFilter.allCases) { Text($0.title).tag($0) } }
                .pickerStyle(.segmented).padding()
            Group {
                switch store.state {
                case .idle where store.items.isEmpty, .loading where store.items.isEmpty: LoadingView()
                case .failed(let message) where store.items.isEmpty: FailureView(message: message) { Task { await store.load() } }
                default:
                    if store.items.isEmpty { EmptyStateView(title: "补货清单为空", message: "添加需要购买的物品。", icon: "cart") }
                    else { List(store.items) { item in row(item) } }
                }
            }
        }
        .navigationTitle("补货")
        .task { async let a: Void = restock.load(); async let b: Void = categories.load(); _ = await (a, b) }
        .task(id: store.selection) { await restock.load() }.refreshableWithCapabilities { await restock.load() }
        .toolbar { Menu { Button("新增补货", systemImage: "plus") { presentation = .add }; if store.selection != .pending { Button("清理已完成项", systemImage: "trash", role: .destructive) { presentation = .confirmClean } } } label: { Image(systemName: "plus.circle") } }
        .sheet(item: sheetBinding) { value in NavigationStack { switch value { case .add: RestockEditorView(item: nil); case .edit(let item): RestockEditorView(item: item); case .complete(let item): CompleteRestockView(item: item); case .confirmDelete, .confirmClean: EmptyView() } } }
        .confirmationDialog("删除补货项目？", isPresented: deleteConfirmation) {
            Button("永久删除", role: .destructive) { if case .confirmDelete(let item) = presentation { Task { await delete(item) } } }
        } message: { Text("删除后无法恢复。") }
        .confirmationDialog("清理所有已完成补货？", isPresented: cleanConfirmation) {
            Button("永久清理", role: .destructive) { Task { await clean() } }
        } message: { Text("待购买项目不会受影响。") }
        .savingOverlay(action.isRunning).actionErrorAlert($action)
    }

    private func row(_ item: RestockItem) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack { Text(item.name).font(.headline); Spacer(); Text(item.status.title).font(.caption.weight(.semibold)).foregroundStyle(item.status == .pending ? .orange : .green) }
            HStack { Text(item.quantityText); if let name = item.category?.name { Text("· \(name)") } }.font(.subheadline).foregroundStyle(.secondary)
            if let notes = item.notes { Text(notes).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
        }.padding(.vertical, 4)
        .contentShape(Rectangle()).swipeActions {
            Button("删除", role: .destructive) { presentation = .confirmDelete(item) }
            Button("编辑") { presentation = .edit(item) }.tint(.blue)
        }.swipeActions(edge: .leading) { if item.status == .pending { Button("已购买") { presentation = .complete(item) }.tint(.green) } }
        .contextMenu { if item.status == .pending { Button("标记购买完成") { presentation = .complete(item) } }; Button("编辑") { presentation = .edit(item) }; Button("删除", role: .destructive) { presentation = .confirmDelete(item) } }
    }

    private var sheetBinding: Binding<RestockPresentation?> { Binding(get: { presentation?.isSheet == true ? presentation : nil }, set: { presentation = $0 }) }
    private var deleteConfirmation: Binding<Bool> { Binding(get: { if case .confirmDelete = presentation { true } else { false } }, set: { if !$0 { presentation = nil } }) }
    private var cleanConfirmation: Binding<Bool> { Binding(get: { if case .confirmClean = presentation { true } else { false } }, set: { if !$0 { presentation = nil } }) }
    private func delete(_ item: RestockItem) async { action = .running; do { try await restock.delete(id: item.id); presentation = nil; action = .idle } catch { action = .failed(error.localizedDescription) } }
    private func clean() async { action = .running; do { try await restock.clean(); presentation = nil; action = .succeeded("清理完成") } catch { action = .failed(error.localizedDescription) } }
}

private struct RestockEditorView: View {
    let item: RestockItem?
    @Environment(\.dismiss) private var dismiss
    @Environment(RestockStore.self) private var restock
    @Environment(CategoryStore.self) private var categories
    @State private var name: String; @State private var category: Int?; @State private var quantity: String
    @State private var unit: String; @State private var notes: String; @State private var action: ActionState = .idle
    init(item: RestockItem?) {
        self.item = item; _name = State(initialValue: item?.name ?? ""); _category = State(initialValue: item?.categoryId)
        _quantity = State(initialValue: item?.quantityValue?.formatted() ?? ""); _unit = State(initialValue: item?.quantityUnit ?? "个"); _notes = State(initialValue: item?.notes ?? "")
    }
    var body: some View {
        Form { Section("补货内容") { TextField("名称", text: $name); Picker("分类（可稍后选择）", selection: $category) { Text("未指定").tag(Int?.none); ForEach(categories.flat) { Text($0.name).tag(Optional($0.id)) } }; TextField("数量", text: $quantity).keyboardType(.decimalPad); TextField("单位", text: $unit) }; Section("备注") { TextEditor(text: $notes).frame(minHeight: 80) } }
            .navigationTitle(item == nil ? "新增补货" : "编辑补货").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("保存") { Task { await save() } }.disabled(name.trimmed.isEmpty || action.isRunning) } }
            .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private func save() async { action = .running; do { try await restock.save(id: item?.id, name: name, category: category, quantity: Double(quantity), unit: unit, notes: notes); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}

private struct CompleteRestockView: View {
    let item: RestockItem
    @Environment(\.dismiss) private var dismiss
    @Environment(RestockStore.self) private var restock
    @Environment(CategoryStore.self) private var categories
    @State private var quantity: String; @State private var category: Int?; @State private var owner = "全家"; @State private var location = ""
    @State private var expiration: ExpirationChoice = .infinite
    @State private var action: ActionState = .idle
    init(item: RestockItem) { self.item = item; _quantity = State(initialValue: item.quantityValue?.formatted() ?? "1"); _category = State(initialValue: item.categoryId) }
    var body: some View {
        Form {
            Section("实际购买") { LabeledValue(label: "物品", value: item.name); TextField("购买数量", text: $quantity).keyboardType(.decimalPad); Picker("分类", selection: $category) { Text("请选择").tag(Int?.none); ForEach(categories.flat) { Text($0.name).tag(Optional($0.id)) } } }
            Section("加入库存") { TextField("所有者", text: $owner); TextField("存放位置", text: $location); Toggle("永久有效", isOn: infiniteBinding); if case .dated = expiration { DatePicker("到期日期", selection: expirationDateBinding, displayedComponents: .date) } }
            if let planned = item.quantityValue { Section { Text("购买少于计划数量 \(planned.formatted()) 时，剩余数量会继续留在待补货清单。") }.font(.footnote).foregroundStyle(.secondary) }
        }.navigationTitle("完成补货").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("确认入库") { Task { await submit() } }.disabled(!valid || action.isRunning) } }
            .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var valid: Bool { Double(quantity).map { $0 > 0 } == true && category != nil && !owner.trimmed.isEmpty && !location.trimmed.isEmpty }
    private var infiniteBinding: Binding<Bool> { Binding(get: { expiration == .infinite }, set: { expiration = $0 ? .infinite : .dated(.now) }) }
    private var expirationDateBinding: Binding<Date> { Binding(get: { if case .dated(let date) = expiration { date } else { .now } }, set: { expiration = .dated($0) }) }
    private func submit() async { guard let value = Double(quantity) else { return }; action = .running; do { try await restock.complete(id: item.id, quantity: value, category: category, owner: owner, location: location, expiration: expiration.apiValue); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}
