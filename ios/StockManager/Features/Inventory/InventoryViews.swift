import SwiftUI

private enum InventoryPresentation: Identifiable {
    case add, edit(StockItem), consume(StockItem), filters, confirmClean
    var id: String { switch self { case .add: "add"; case .edit(let i): "edit-\(i.id)"; case .consume(let i): "consume-\(i.id)"; case .filters: "filters"; case .confirmClean: "clean" } }
    var isSheet: Bool { if case .confirmClean = self { false } else { true } }
}

struct InventoryListView: View {
    @Environment(InventoryStore.self) private var inventory
    @Environment(CategoryStore.self) private var categories
    @Environment(IntakeStore.self) private var intake
    @Environment(CapabilitiesStore.self) private var capabilities
    @State private var presentation: InventoryPresentation?
    @State private var showsIntake = false
    @State private var action: ActionState = .idle

    var body: some View {
        @Bindable var store = inventory
        Group {
            switch store.state {
            case .idle where store.items.isEmpty, .loading where store.items.isEmpty: LoadingView()
            case .failed(let message) where store.items.isEmpty: FailureView(message: message) { Task { await store.load() } }
            default:
                if store.items.isEmpty { EmptyStateView(title: "没有库存", message: "添加第一件家庭物品，或调整搜索与筛选条件。", icon: "shippingbox") }
                else {
                    List(store.items) { item in
                        NavigationLink { ItemDetailView(itemID: item.id) } label: { ItemRow(item: item) }
                            .swipeActions(edge: .leading) { Button("消耗") { presentation = .consume(item) }.tint(.orange) }
                    }.listStyle(.insetGrouped)
                }
            }
        }
        .navigationTitle("库存")
        .searchable(text: $store.query, prompt: "搜索名称、分类、所有者或位置")
        .task(id: store.query) { try? await Task.sleep(for: .milliseconds(300)); guard !Task.isCancelled else { return }; await store.load() }
        .task { async let a: Void = inventory.load(); async let b: Void = categories.load(); _ = await (a, b) }
        .refreshableWithCapabilities { await inventory.load() }
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if capabilities.value.ai.text || capabilities.value.ai.vision || capabilities.value.ai.asr ||
                    !intake.candidates.isEmpty || intake.photoUpload != nil {
                    Button("AI 入库", systemImage: "sparkles") { showsIntake = true }
                        .accessibilityIdentifier("inventory.aiIntake")
                }
                Button { presentation = .filters } label: { Image(systemName: activeFilters ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle") }
                Menu {
                    Button("新增库存", systemImage: "plus") { presentation = .add }
                    Divider(); Button("清理已消耗/过期项", systemImage: "trash", role: .destructive) { presentation = .confirmClean }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
        .fullScreenCover(isPresented: $showsIntake) {
            NavigationStack { IntakeReviewView(store: intake) }
        }
        .sheet(item: sheetBinding) { value in
            NavigationStack {
                switch value {
                case .add: ItemEditorView(item: nil)
                case .edit(let item): ItemEditorView(item: item)
                case .consume(let item): ConsumeItemView(item: item)
                case .filters: InventoryFilterView()
                case .confirmClean: EmptyView()
                }
            }
        }
        .confirmationDialog("清理库存", isPresented: cleanConfirmation, titleVisibility: .visible) {
            Button("删除已消耗和已过期项目", role: .destructive) { Task { await clean() } }
            Button("取消", role: .cancel) {}
        } message: { Text("此操作会永久删除服务器中的已完成记录，无法撤销。") }
        .savingOverlay(action.isRunning).actionErrorAlert($action)
    }

    private var activeFilters: Bool { inventory.filters.categoryId != nil || inventory.filters.owner != nil || inventory.filters.location != nil || inventory.filters.status != nil }
    private var sheetBinding: Binding<InventoryPresentation?> { Binding(get: { presentation?.isSheet == true ? presentation : nil }, set: { presentation = $0 }) }
    private var cleanConfirmation: Binding<Bool> { Binding(get: { presentation?.id == "clean" }, set: { if !$0 { presentation = nil } }) }
    private func clean() async { action = .running; do { try await inventory.clean([.consumed, .expired]); presentation = nil; action = .succeeded("清理完成") } catch { action = .failed(error.localizedDescription) } }
}

private struct ItemRow: View {
    let item: StockItem
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack { Text(item.name).font(.headline); Spacer(); StatusBadge(status: item.status) }
            HStack { Label(item.quantityText, systemImage: "scalemass"); Label(item.location, systemImage: "mappin") }.font(.subheadline).foregroundStyle(.secondary)
            HStack { Text(item.category.name); Spacer(); Text(item.expirationText) }.font(.caption).foregroundStyle(.secondary)
        }.padding(.vertical, 4)
    }
}

private struct InventoryFilterView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(InventoryStore.self) private var inventory
    @Environment(CategoryStore.self) private var categories
    var body: some View {
        @Bindable var store = inventory
        Form {
            Picker("分类", selection: $store.filters.categoryId) { Text("全部").tag(Int?.none); ForEach(categories.flat) { Text($0.name).tag(Optional($0.id)) } }
            Picker("状态", selection: $store.filters.status) { Text("全部").tag(ItemStatus?.none); ForEach(ItemStatus.allCases) { Text($0.title).tag(Optional($0)) } }
            TextField("所有者", text: Binding(get: { store.filters.owner ?? "" }, set: { store.filters.owner = $0.nilIfBlank }))
            TextField("位置", text: Binding(get: { store.filters.location ?? "" }, set: { store.filters.location = $0.nilIfBlank }))
            Button("清除全部筛选", role: .destructive) { store.filters = .init() }
        }.navigationTitle("筛选").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { Task { await store.load(); dismiss() } } } }
    }
}

struct ItemDetailView: View {
    let itemID: Int
    @Environment(\.dismiss) private var dismiss
    @Environment(InventoryStore.self) private var inventory
    @State private var state: LoadState<StockItem> = .idle
    @State private var presentation: ItemDetailPresentation?
    @State private var action: ActionState = .idle
    var body: some View {
        Group {
            switch state {
            case .idle, .loading:
                LoadingView()
            case .failed(let message):
                FailureView(message: message) { Task { await reload() } }
            case .loaded(let item):
                List {
                    Section { ItemRow(item: item) }
                    Section("详情") {
                        LabeledValue(label: "分类", value: item.category.name); LabeledValue(label: "所有者", value: item.owner)
                        LabeledValue(label: "购买日期", value: item.purchaseDate); LabeledValue(label: "存放位置", value: item.location)
                        LabeledValue(label: "未开封保质期", value: item.unopenedExpirationDate == "infinite" ? "永久有效" : item.unopenedExpirationDate)
                        if let value = item.openedDate { LabeledValue(label: "开封日期", value: value) }
                        if let value = item.openedExpirationDate { LabeledValue(label: "开封后到期", value: value) }
                    }
                    if let notes = item.notes, !notes.isEmpty { Section("备注") { Text(notes) } }
                    Section {
                        Button("消耗库存", systemImage: "minus.circle") { presentation = .consume(item) }
                        Button("删除库存", systemImage: "trash", role: .destructive) { presentation = .confirmDelete(item) }
                    }
                }
            }
        }
        .navigationTitle(loadedItem?.name ?? "库存详情").navigationBarTitleDisplayMode(.inline)
        .toolbar { if let item = loadedItem { Button("编辑") { presentation = .edit(item) } } }
        .task { await reload() }
        .sheet(item: detailSheetBinding, onDismiss: { Task { await reload() } }) { value in
            NavigationStack { switch value { case .edit(let item): ItemEditorView(item: item); case .consume(let item): ConsumeItemView(item: item); case .confirmDelete: EmptyView() } }
        }
        .confirmationDialog("删除“\(loadedItem?.name ?? "")”？", isPresented: deleteConfirmation) {
            Button("永久删除", role: .destructive) { Task { await delete() } }
        } message: { Text("此操作无法撤销。需要补货时，可先消耗并选择加入补货清单。") }
        .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var loadedItem: StockItem? { if case .loaded(let item) = state { item } else { nil } }
    private var detailSheetBinding: Binding<ItemDetailPresentation?> { Binding(get: { presentation?.isSheet == true ? presentation : nil }, set: { presentation = $0 }) }
    private var deleteConfirmation: Binding<Bool> { Binding(get: { if case .confirmDelete = presentation { true } else { false } }, set: { if !$0 { presentation = nil } }) }
    private func reload() async { state = .loading; do { state = .loaded(try await inventory.client.item(id: itemID)) } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) } }
    private func delete() async { action = .running; do { try await inventory.delete(id: itemID); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}

private enum ItemDetailPresentation: Identifiable {
    case edit(StockItem), consume(StockItem), confirmDelete(StockItem)
    var id: String { switch self { case .edit(let item): "edit-\(item.id)"; case .consume(let item): "consume-\(item.id)"; case .confirmDelete(let item): "delete-\(item.id)" } }
    var isSheet: Bool { if case .confirmDelete = self { false } else { true } }
}

struct ItemEditorView: View {
    let item: StockItem?
    @Environment(\.dismiss) private var dismiss
    @Environment(InventoryStore.self) private var inventory
    @Environment(CategoryStore.self) private var categories
    @State private var draft: ItemDraft
    @State private var action: ActionState = .idle
    init(item: StockItem?) { self.item = item; _draft = State(initialValue: item.map(ItemDraft.init) ?? ItemDraft()) }
    var body: some View {
        Form {
            Section("基本信息") {
                InventoryTextField(.name, text: $draft.name)
                InventoryCategoryPicker(categories: categories.flat, selection: $draft.categoryId)
                InventoryTextField(.owner, text: $draft.owner)
                InventoryTextField(.location, text: $draft.location)
                DatePicker("购买日期", selection: purchaseDateBinding, displayedComponents: .date)
            }
            Section("数量") {
                InventoryTextField(.quantity, text: $draft.quantity)
                InventoryTextField(.unit, text: $draft.unit)
            }
            Section("有效期") {
                Toggle("永久有效", isOn: unopenedInfiniteBinding)
                if case .dated = draft.unopenedExpiration { DatePicker("未开封到期", selection: unopenedDateBinding, displayedComponents: .date) }
                if draft.unopenedExpirationSource == .categoryDefault {
                    Text("按分类默认保质期").font(.caption).foregroundStyle(.secondary)
                }
                Toggle("已开封", isOn: openedBinding)
                if case .opened = draft.opening {
                    DatePicker("开封日期", selection: openedDateBinding, displayedComponents: .date)
                    Toggle("设置开封后有效期", isOn: openedExpirationEnabledBinding)
                    if openedExpirationEnabledBinding.wrappedValue {
                        Toggle("开封后永久有效", isOn: openedExpirationInfiniteBinding)
                        if !openedExpirationInfiniteBinding.wrappedValue { DatePicker("开封后到期", selection: openedExpirationDateBinding, displayedComponents: .date) }
                    }
                }
            }
            Section("备注") { TextEditor(text: $draft.notes).frame(minHeight: 90) }
        }
        .navigationTitle(item == nil ? "新增库存" : "编辑库存").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) { Button("保存") { Task { await save() } }.disabled(!valid || action.isRunning) }
        }
        .task { if categories.flat.isEmpty { await categories.load() } }
        .task { await loadDefaultPurchaseDate() }
        .onChange(of: selectedShelfLife, initial: true) { applySelectedShelfLife() }
        .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var valid: Bool { !draft.name.trimmed.isEmpty && draft.categoryId != nil && !draft.owner.trimmed.isEmpty && Double(draft.quantity).map { $0 > 0 } == true && !draft.unit.trimmed.isEmpty && !draft.location.trimmed.isEmpty }
    private var selectedShelfLife: Int? { categories.flat.first { $0.id == draft.categoryId }?.defaultShelfLifeDays }
    private var purchaseDateBinding: Binding<Date> {
        Binding(get: { draft.purchaseDate }, set: { date in
            draft.setPurchaseDate(date)
            applySelectedShelfLife()
        })
    }
    private var unopenedInfiniteBinding: Binding<Bool> {
        Binding(get: { draft.unopenedExpiration == .infinite },
                set: { draft.setUnopenedExpiration($0 ? .infinite : .dated(.now)) })
    }
    private var unopenedDateBinding: Binding<Date> {
        Binding(get: { if case .dated(let date) = draft.unopenedExpiration { date } else { .now } },
                set: { draft.setUnopenedExpiration(.dated($0)) })
    }
    private func applySelectedShelfLife() {
        guard item == nil else { return }
        draft.applyShelfLife(selectedShelfLife)
    }
    private func loadDefaultPurchaseDate() async {
        guard item == nil,
              let settings = try? await inventory.client.settings(), !Task.isCancelled,
              let identifier = settings.defaultTimezone, let timeZone = TimeZone(identifier: identifier) else { return }
        draft.useHouseholdToday(.now, in: timeZone)
        applySelectedShelfLife()
    }
    private var openedBinding: Binding<Bool> { Binding(get: { if case .opened = draft.opening { true } else { false } }, set: { draft.opening = $0 ? .opened(date: .now, expiration: nil) : .unopened }) }
    private var openedDateBinding: Binding<Date> { Binding(get: { if case .opened(let date, _) = draft.opening { date } else { .now } }, set: { newDate in if case .opened(_, let expiration) = draft.opening { draft.opening = .opened(date: newDate, expiration: expiration) } }) }
    private var openedExpirationEnabledBinding: Binding<Bool> { Binding(get: { if case .opened(_, .some) = draft.opening { true } else { false } }, set: { enabled in if case .opened(let date, _) = draft.opening { draft.opening = .opened(date: date, expiration: enabled ? .dated(.now) : nil) } }) }
    private var openedExpirationInfiniteBinding: Binding<Bool> { Binding(get: { if case .opened(_, .some(.infinite)) = draft.opening { true } else { false } }, set: { infinite in if case .opened(let date, _) = draft.opening { draft.opening = .opened(date: date, expiration: infinite ? .infinite : .dated(.now)) } }) }
    private var openedExpirationDateBinding: Binding<Date> { Binding(get: { if case .opened(_, .some(.dated(let date))) = draft.opening { date } else { .now } }, set: { newDate in if case .opened(let date, _) = draft.opening { draft.opening = .opened(date: date, expiration: .dated(newDate)) } }) }
    private func save() async { action = .running; do { try await inventory.save(draft, editing: item?.id); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}

struct ConsumeItemView: View {
    let item: StockItem
    @Environment(\.dismiss) private var dismiss
    @Environment(InventoryStore.self) private var inventory
    @State private var quantity = ""; @State private var addToRestock = false; @State private var action: ActionState = .idle
    @FocusState private var quantityFocused: Bool
    var body: some View {
        Form {
            Section {
                LabeledValue(label: "当前库存", value: item.quantityText)
                TextField("消耗数量（\(item.quantityUnit)）", text: $quantity)
                    .keyboardType(.decimalPad)
                    .focused($quantityFocused)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("inventory.consume.quantity")
                if !quantity.trimmed.isEmpty && parsedQuantity == nil {
                    Text("请输入有效数字，可使用小数点或本地小数分隔符。")
                        .font(.caption).foregroundStyle(.red)
                } else if let value = parsedQuantity, value > item.quantityValue {
                    Text("不能超过当前库存 \(item.quantityText)。")
                        .font(.caption).foregroundStyle(.red)
                }
                Toggle("加入补货清单", isOn: $addToRestock)
            }
        }.navigationTitle("消耗 \(item.name)").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("确认") { Task { await submit() } }.disabled(!valid || action.isRunning) }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if quantityFocused {
                    HStack {
                        Spacer()
                        Button("完成") { quantityFocused = false }
                            .fontWeight(.semibold)
                    }
                    .padding(.horizontal)
                    .frame(minHeight: 44)
                    .background(.bar)
                }
            }
            .onAppear { quantityFocused = true }
            .savingOverlay(action.isRunning).actionErrorAlert($action)
    }
    private var parsedQuantity: Double? { quantity.quantityValue() }
    private var valid: Bool { parsedQuantity.map { $0 > 0 && $0 <= item.quantityValue } == true }
    private func submit() async { guard let value = parsedQuantity else { return }; quantityFocused = false; action = .running; do { try await inventory.consume(id: item.id, quantity: value, addToRestock: addToRestock); action = .succeeded(nil); dismiss() } catch { action = .failed(error.localizedDescription) } }
}

#if DEBUG
struct ConsumeItemTestHost: View {
    @State private var inventory = InventoryStore(client: APIClient(
        baseURL: URL(string: "https://ui-test.invalid/api")!, token: "ui-test"
    ))

    var body: some View {
        NavigationStack { ConsumeItemView(item: Self.item) }
            .environment(inventory)
    }

    private static let category = Category(
        id: 1, name: "测试分类", slug: "ui-test", parentId: nil,
        recipeUsage: .always, isSystem: false, sortOrder: 0, children: nil
    )
    private static let item = StockItem(
        id: 1, name: "测试库存", categoryId: 1, category: category,
        owner: "全家", purchaseDate: "2026-11-17", quantityValue: 5,
        quantityUnit: "份", location: "冰箱", unopenedExpirationDate: "infinite",
        openedExpirationDate: nil, openedDate: nil, currentExpirationDate: "infinite",
        status: .active, notes: nil, createdAt: nil, updatedAt: nil
    )
}
#endif

struct ReminderView: View {
    @Environment(InventoryStore.self) private var inventory
    @State private var state: LoadState<[StockItem]> = .idle
    var body: some View {
        Group { switch state { case .idle, .loading: LoadingView(); case .failed(let message): FailureView(message: message) { Task { await load() } }; case .loaded(let items): if items.isEmpty { EmptyStateView(title: "没有过期提醒", message: "当前库存都在安全期限内。", icon: "checkmark.circle") } else { List { reminderSection("即将过期", items: items.filter { $0.status == .expiringSoon }); reminderSection("已经过期", items: items.filter { $0.status == .expired }) } } } }
            .navigationTitle("过期提醒").task { await load() }.refreshableWithCapabilities { await load() }
    }
    @ViewBuilder private func reminderSection(_ title: String, items: [StockItem]) -> some View { if !items.isEmpty { Section(title) { ForEach(items) { item in NavigationLink { ItemDetailView(itemID: item.id) } label: { ItemRow(item: item) } } } } }
    private func load() async { state = .loading; do { state = .loaded(try await inventory.client.reminders()) } catch { state = .failed(error.localizedDescription) } }
}
