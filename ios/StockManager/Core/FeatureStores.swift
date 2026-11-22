import Foundation
import Observation

@MainActor @Observable
final class InventoryStore {
    let client: any APIClientProtocol
    var state: LoadPhase = .idle
    var items: [StockItem] = []
    var query = ""
    var filters = ItemFilters()

    init(client: any APIClientProtocol) { self.client = client }

    func load() async {
        state = .loading
        do {
            items = query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? try await client.items(filters: filters)
                : try await client.searchItems(query, filters: filters)
            state = .loaded
        } catch is CancellationError { return }
        catch { state = .failed(error.localizedDescription) }
    }

    func save(_ draft: ItemDraft, editing id: Int?) async throws {
        guard let categoryId = draft.categoryId, let quantity = Double(draft.quantity), quantity > 0 else {
            throw APIClientError.server(status: 422, code: nil, params: [:], fallback: "请选择分类并输入有效数量")
        }
        let expiration = draft.unopenedExpiration.apiValue
        let openedDate: String?
        let openedExpiration: String?
        switch draft.opening {
        case .unopened:
            openedDate = nil; openedExpiration = nil
        case .opened(let date, let choice):
            openedDate = API.string(date); openedExpiration = choice?.apiValue
        }
        if let id {
            let body = ItemUpdate(name: draft.name.trimmed, categoryId: categoryId, owner: draft.owner.trimmed,
                purchaseDate: API.string(draft.purchaseDate), quantityValue: quantity, quantityUnit: draft.unit.trimmed,
                location: draft.location.trimmed, unopenedExpirationDate: expiration,
                openedExpirationDate: openedExpiration, openedDate: openedDate, notes: draft.notes.nilIfBlank)
            _ = try await client.updateItem(id: id, body)
        } else {
            let body = ItemCreate(name: draft.name.trimmed, categoryId: categoryId, owner: draft.owner.trimmed,
                purchaseDate: draft.explicitPurchaseDate, quantityValue: quantity, quantityUnit: draft.unit.trimmed,
                location: draft.location.trimmed, unopenedExpirationDate: expiration,
                openedExpirationDate: openedExpiration, openedDate: openedDate,
                currentExpirationDate: openedDate != nil ? (openedExpiration ?? expiration) : expiration,
                notes: draft.notes.nilIfBlank)
            _ = try await client.createItem(body)
        }
        await load()
    }

    func consume(id: Int, quantity: Double, addToRestock: Bool) async throws {
        _ = try await client.consumeItem(id: id, .init(quantity: quantity, addToRestock: addToRestock)); await load()
    }
    func delete(id: Int) async throws { try await client.deleteItem(id: id); await load() }
    func clean(_ statuses: [ItemStatus]) async throws { _ = try await client.cleanItems(statuses: statuses); await load() }
}

@MainActor @Observable
final class CategoryStore {
    let client: any APIClientProtocol
    var state: LoadPhase = .idle
    var tree: [Category] = []
    var flat: [Category] = []
    init(client: any APIClientProtocol) { self.client = client }
    func load() async {
        state = .loading
        do { async let a = client.categories(tree: true); async let b = client.categories(tree: false); (tree, flat) = try await (a, b); state = .loaded }
        catch { state = .failed(error.localizedDescription) }
    }
    func create(name: String, parent: Int?, usage: RecipeUsage, order: Int, shelfLife: Int?) async throws {
        _ = try await client.createCategory(.init(name: name.trimmed, parentId: parent,
                                                  recipeUsage: usage, sortOrder: order, defaultShelfLifeDays: shelfLife))
        await load()
    }
    func update(_ category: Category, name: String, parent: Int?, usage: RecipeUsage, order: Int, shelfLife: Int?) async throws {
        let body = CategoryUpdate(name: category.isSystem ? nil : name.trimmed,
                                  parentId: parent, includeParentId: !category.isSystem,
                                  recipeUsage: usage, sortOrder: order, defaultShelfLifeDays: shelfLife,
                                  includeDefaultShelfLifeDays: shelfLife != category.defaultShelfLifeDays)
        _ = try await client.updateCategory(id: category.id, body)
        await load()
    }
    func delete(_ category: Category) async throws { try await client.deleteCategory(id: category.id); await load() }
}

@MainActor @Observable
final class RestockStore {
    let client: any APIClientProtocol
    var state: LoadPhase = .idle
    var items: [RestockItem] = []
    var selection: RestockFilter = .pending
    init(client: any APIClientProtocol) { self.client = client }
    func load() async {
        state = .loading
        do { items = try await client.restockItems(status: selection.apiValue); state = .loaded }
        catch { state = .failed(error.localizedDescription) }
    }
    func save(id: Int?, name: String, category: Int?, quantity: Double?, unit: String, notes: String) async throws {
        if let id { _ = try await client.updateRestock(id: id, .init(name: name.trimmed, categoryId: category, quantityValue: quantity, quantityUnit: unit.nilIfBlank, status: nil, notes: notes.nilIfBlank)) }
        else { _ = try await client.createRestock(.init(name: name.trimmed, categoryId: category, quantityValue: quantity, quantityUnit: unit.nilIfBlank, sourceItemId: nil, notes: notes.nilIfBlank)) }
        await load()
    }
    func complete(id: Int, quantity: Double, category: Int?, owner: String, location: String, expiration: String) async throws {
        _ = try await client.completeRestock(id: id, .init(purchasedQuantity: quantity, categoryId: category,
            owner: owner.nilIfBlank, purchaseDate: API.string(.now), location: location.nilIfBlank,
            unopenedExpirationDate: expiration, openedExpirationDate: nil, openedDate: nil)); await load()
    }
    func delete(id: Int) async throws { try await client.deleteRestock(id: id); await load() }
    func clean() async throws { _ = try await client.cleanRestock(); await load() }
}

enum RestockFilter: String, CaseIterable, Identifiable {
    case pending, done, all
    var id: String { rawValue }
    var title: String { switch self { case .pending: "待购买"; case .done: "已完成"; case .all: "全部" } }
    var apiValue: String? { self == .all ? nil : rawValue }
}

@MainActor @Observable
final class RecipeStore {
    let client: any APIClientProtocol
    var state: LoadPhase = .idle
    var recipes: [RecipeSummary] = []
    var query = ""; var source: RecipeSourceFilter?; var category: RecipeCategory?; var favoritesOnly = false
    private(set) var pagination: PaginationState = .ready
    private var generation = UUID()
    private let pageSize = 30
    var canLoadMore: Bool { pagination == .ready }
    init(client: any APIClientProtocol) { self.client = client }
    func load(reset: Bool = true) async {
        let requestGeneration: UUID
        let requestOffset: Int
        if reset {
            generation = UUID()
            requestGeneration = generation
            requestOffset = 0
            recipes = []
            state = .loading
        } else {
            guard pagination == .ready else { return }
            requestGeneration = generation
            requestOffset = recipes.count
        }
        pagination = .loading
        do {
            let page = try await client.recipes(query: query.nilIfBlank, source: source?.rawValue, category: category?.rawValue,
                favoritesOnly: favoritesOnly, limit: pageSize, offset: requestOffset)
            guard requestGeneration == generation else { return }
            recipes += page; pagination = page.count == pageSize ? .ready : .exhausted; state = .loaded
        } catch is CancellationError {
            guard requestGeneration == generation else { return }
            pagination = .ready; state = recipes.isEmpty ? .idle : .loaded
        } catch {
            guard requestGeneration == generation else { return }
            pagination = .ready; state = .failed(error.localizedDescription)
        }
    }
    func recommendations(scene: RecommendationScene) async throws -> RecommendationSnapshot {
        let recommendationResponse = try await client.recommendations(scene: scene.rawValue)
        if !recommendationResponse.recommendations.isEmpty {
            return RecommendationSnapshot(
                recommendations: recommendationResponse.recommendations,
                hasRecipes: true,
                eligibleInventoryCount: nil
            )
        }
        async let recipePage = client.recipes(query: nil, source: nil, category: nil,
            favoritesOnly: false, limit: 1, offset: 0)
        async let inventoryPage = client.items(filters: .init())
        let (recipes, inventory) = try await (recipePage, inventoryPage)
        let eligibleCount = inventory.filter {
            [.active, .expiringSoon].contains($0.status) && $0.category.recipeUsage != .never
        }.count
        return RecommendationSnapshot(
            recommendations: [],
            hasRecipes: !recipes.isEmpty,
            eligibleInventoryCount: eligibleCount
        )
    }
    func favorite(id: Int, value: Bool) async throws { try await client.setFavorite(id: id, favorite: value); await load() }
    func delete(id: Int) async throws { try await client.deleteRecipe(id: id); await load() }
}

enum PaginationState: Equatable {
    case ready
    case loading
    case exhausted
}

enum RecipeSourceFilter: String, CaseIterable, Identifiable {
    case howToCook = "howtocook"
    case user
    case aiSaved = "ai_saved"

    var id: String { rawValue }
    var title: String { switch self { case .howToCook: "HowToCook"; case .user: "我的菜谱"; case .aiSaved: "AI 保存" } }
}

enum RecommendationScene: String, CaseIterable, Identifiable {
    case all, breakfast, meal
    case dessertDrink = "dessert_drink"

    var id: String { rawValue }
    var title: String { switch self { case .all: "全部"; case .breakfast: "早餐"; case .meal: "正餐"; case .dessertDrink: "甜点饮品" } }
}

struct RecommendationSnapshot {
    let recommendations: [RecipeRecommendation]
    let hasRecipes: Bool
    let eligibleInventoryCount: Int?

    var emptyMessage: String {
        if !hasRecipes {
            return "菜谱库还是空的。请先创建菜谱，或在服务器上导入 HowToCook；只有库存无法生成推荐。"
        }
        if eligibleInventoryCount == 0 {
            return "当前库存没有可用于菜谱的有效物品。请检查库存状态和分类的菜谱用途。"
        }
        return "当前库存与这个场景下的菜谱匹配不足。可以切换到“全部”，或补充菜谱与食材。"
    }
}

extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
    var nilIfBlank: String? { trimmed.isEmpty ? nil : trimmed }

    var shelfLifeDays: Int? {
        Int((applyingTransform(.fullwidthToHalfwidth, reverse: false) ?? self).trimmed)
    }

    /// Parses quantities typed with localized/full-width decimal characters.
    /// The backend still receives a normal `Double` regardless of keyboard locale.
    func quantityValue(locale: Locale = .current) -> Double? {
        var normalized = applyingTransform(.fullwidthToHalfwidth, reverse: false) ?? self
        normalized = normalized.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "\u{00A0}", with: "")
        let separators = Set([locale.decimalSeparator, ".", ",", "，", "٫"].compactMap { $0 })
        for separator in separators where separator != "." {
            normalized = normalized.replacingOccurrences(of: separator, with: ".")
        }
        guard normalized.filter({ $0 == "." }).count <= 1,
              normalized.allSatisfy({ $0.isNumber || $0 == "." }) else { return nil }
        return Double(normalized)
    }
}
