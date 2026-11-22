import Foundation

enum LoadState<Value> {
    case idle, loading
    case loaded(Value)
    case failed(String)
}

enum ItemStatus: String, Codable, CaseIterable, Identifiable {
    case active
    case consumed
    case expiringSoon = "expiring soon"
    case expired

    var id: String { rawValue }
    var title: String {
        switch self {
        case .active: "有效"
        case .consumed: "已消耗"
        case .expiringSoon: "即将过期"
        case .expired: "已过期"
        }
    }
}

enum RestockStatus: String, Codable, CaseIterable, Identifiable {
    case pending, done
    var id: String { rawValue }
    var title: String { self == .pending ? "待购买" : "已完成" }
}

enum RecipeUsage: Codable, CaseIterable, Hashable, Identifiable {
    case always, conditional, never, unknown(String)

    static let allCases: [Self] = [.always, .conditional, .never]
    var id: String { rawValue }
    var title: String { DisplayText.recipeUsage(rawValue) }

    var rawValue: String {
        switch self {
        case .always: "always"
        case .conditional: "conditional"
        case .never: "never"
        case .unknown(let value): value
        }
    }

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self.allCases.first { $0.rawValue == value } ?? .unknown(value)
    }

    func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        try value.encode(rawValue)
    }
}

struct HealthResponse: Codable, Hashable { let status: String; let version: String }
struct MessageResponse: Codable, Hashable { let message: String }
struct AppSettings: Codable, Hashable {
    let expirationReminderDays: String
    var defaultLocale: String? = nil
    var defaultTimezone: String? = nil
}
struct SettingsUpdate: Encodable {
    var expirationReminderDays: String?
    var defaultLocale: String?
    var defaultTimezone: String?
}

struct Capabilities: Decodable, Equatable, Sendable {
    struct AI: Decodable, Equatable, Sendable {
        let text: Bool
        let vision: Bool
        let asr: Bool
    }

    let ai: AI
    static let unavailable = Self(ai: AI(text: false, vision: false, asr: false))
}

struct Category: Codable, Identifiable, Hashable {
    let id: Int
    var name: String
    var slug: String
    var parentId: Int?
    var recipeUsage: RecipeUsage
    var isSystem: Bool
    var sortOrder: Int
    var children: [Category]?
    var defaultShelfLifeDays: Int? = nil
}

struct CategoryCreate: Encodable {
    let name: String
    let parentId: Int?
    let recipeUsage: RecipeUsage?
    let sortOrder: Int
    var defaultShelfLifeDays: Int? = nil
}

struct CategoryUpdate: Encodable {
    let name: String?
    let parentId: Int?
    let includeParentId: Bool
    let recipeUsage: RecipeUsage?
    let sortOrder: Int?
    var defaultShelfLifeDays: Int? = nil
    var includeDefaultShelfLifeDays = false

    enum CodingKeys: String, CodingKey { case name, parentId, recipeUsage, sortOrder, defaultShelfLifeDays }
    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encodeIfPresent(name, forKey: .name)
        if includeParentId { if let parentId { try values.encode(parentId, forKey: .parentId) } else { try values.encodeNil(forKey: .parentId) } }
        try values.encodeIfPresent(recipeUsage, forKey: .recipeUsage)
        try values.encodeIfPresent(sortOrder, forKey: .sortOrder)
        if includeDefaultShelfLifeDays {
            try values.encode(defaultShelfLifeDays, forKey: .defaultShelfLifeDays)
        }
    }
}

struct StockItem: Codable, Identifiable, Hashable {
    let id: Int
    var name: String
    var categoryId: Int
    var category: Category
    var owner: String
    var purchaseDate: String
    var quantityValue: Double
    var quantityUnit: String
    var location: String
    var unopenedExpirationDate: String
    var openedExpirationDate: String?
    var openedDate: String?
    var currentExpirationDate: String
    var status: ItemStatus
    var notes: String?
    var createdAt: String?
    var updatedAt: String?

    var quantityText: String { "\(quantityValue.formatted()) \(quantityUnit)" }
    var expirationText: String { currentExpirationDate == "infinite" ? "永久有效" : currentExpirationDate }
}

struct ItemDraft: Hashable {
    var name = ""
    var categoryId: Int?
    var owner = ""
    private(set) var purchaseDate = Date()
    private(set) var didEditPurchaseDate = false
    var quantity = "1"
    var unit = "个"
    var location = ""
    private(set) var unopenedExpiration: ExpirationChoice = .dated(.now)
    private(set) var unopenedExpirationSource: UnopenedExpirationSource = .initial
    var opening: OpeningChoice = .unopened
    var notes = ""

    init() {}
    init(item: StockItem) {
        name = item.name; categoryId = item.categoryId; owner = item.owner
        purchaseDate = API.date(item.purchaseDate) ?? .now
        quantity = item.quantityValue.formatted(); unit = item.quantityUnit; location = item.location
        unopenedExpiration = item.unopenedExpirationDate == "infinite" ? .infinite : .dated(API.date(item.unopenedExpirationDate) ?? .now)
        if let opened = API.date(item.openedDate) {
            let openedExpiration = item.openedExpirationDate.map { $0 == "infinite" ? ExpirationChoice.infinite : .dated(API.date($0) ?? .now) }
            opening = .opened(date: opened, expiration: openedExpiration)
        }
        notes = item.notes ?? ""
    }

    var explicitPurchaseDate: String? {
        didEditPurchaseDate ? API.string(purchaseDate) : nil
    }

    mutating func setPurchaseDate(_ date: Date) {
        purchaseDate = date
        didEditPurchaseDate = true
    }

    mutating func useHouseholdToday(_ now: Date, in timeZone: TimeZone,
                                     calendar: Calendar = Calendar(identifier: .gregorian)) {
        guard !didEditPurchaseDate else { return }
        var householdCalendar = calendar
        householdCalendar.timeZone = timeZone
        let day = householdCalendar.dateComponents([.year, .month, .day], from: now)
        if let localDate = calendar.date(from: day) {
            purchaseDate = localDate
            if unopenedExpirationSource == .initial { unopenedExpiration = .dated(localDate) }
        }
    }

    mutating func setUnopenedExpiration(_ expiration: ExpirationChoice) {
        unopenedExpiration = expiration
        unopenedExpirationSource = .manual
    }

    mutating func applyShelfLife(_ days: Int?, calendar: Calendar = Calendar(identifier: .gregorian)) {
        guard unopenedExpirationSource != .manual else { return }
        if let days, let date = calendar.date(byAdding: .day, value: days, to: purchaseDate) {
            unopenedExpiration = .dated(date)
            unopenedExpirationSource = .categoryDefault
        } else if unopenedExpirationSource == .categoryDefault {
            unopenedExpiration = .dated(purchaseDate)
            unopenedExpirationSource = .initial
        }
    }
}

enum UnopenedExpirationSource: Hashable {
    case initial
    case categoryDefault
    case manual
}

enum OpeningChoice: Hashable {
    case unopened
    case opened(date: Date, expiration: ExpirationChoice?)
}

struct ItemCreate: Encodable {
    let name: String; let categoryId: Int; let owner: String; let purchaseDate: String?
    let quantityValue: Double; let quantityUnit: String; let location: String
    let unopenedExpirationDate: String; let openedExpirationDate: String?; let openedDate: String?
    let currentExpirationDate: String; let notes: String?
}

struct ItemUpdate: Encodable {
    let name: String?; let categoryId: Int?; let owner: String?; let purchaseDate: String?
    let quantityValue: Double?; let quantityUnit: String?; let location: String?
    let unopenedExpirationDate: String?; let openedExpirationDate: String?; let openedDate: String?
    let notes: String?

    enum CodingKeys: String, CodingKey { case name, categoryId, owner, purchaseDate, quantityValue, quantityUnit, location, unopenedExpirationDate, openedExpirationDate, openedDate, notes }
    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encodeIfPresent(name, forKey: .name); try values.encodeIfPresent(categoryId, forKey: .categoryId)
        try values.encodeIfPresent(owner, forKey: .owner); try values.encodeIfPresent(purchaseDate, forKey: .purchaseDate)
        try values.encodeIfPresent(quantityValue, forKey: .quantityValue); try values.encodeIfPresent(quantityUnit, forKey: .quantityUnit)
        try values.encodeIfPresent(location, forKey: .location); try values.encodeIfPresent(unopenedExpirationDate, forKey: .unopenedExpirationDate)
        if let openedExpirationDate { try values.encode(openedExpirationDate, forKey: .openedExpirationDate) } else { try values.encodeNil(forKey: .openedExpirationDate) }
        if let openedDate { try values.encode(openedDate, forKey: .openedDate) } else { try values.encodeNil(forKey: .openedDate) }
        if let notes { try values.encode(notes, forKey: .notes) } else { try values.encodeNil(forKey: .notes) }
    }
}

struct ConsumeRequest: Encodable { let quantity: Double; let addToRestock: Bool }

struct RestockItem: Codable, Identifiable, Hashable {
    let id: Int
    var name: String
    var categoryId: Int?
    var category: Category?
    var quantityValue: Double?
    var quantityUnit: String?
    var sourceItemId: Int?
    var status: RestockStatus
    var notes: String?
    var createdAt: String?
    var doneAt: String?
    var quantityText: String { quantityValue.map { "\($0.formatted()) \(quantityUnit ?? "")" } ?? "未指定" }
}

struct RestockCreate: Encodable {
    let name: String; let categoryId: Int?; let quantityValue: Double?; let quantityUnit: String?
    let sourceItemId: Int?; let notes: String?
}
struct RestockUpdate: Encodable {
    let name: String?; let categoryId: Int?; let quantityValue: Double?; let quantityUnit: String?
    let status: String?; let notes: String?
}
struct RestockDone: Encodable {
    let purchasedQuantity: Double; let categoryId: Int?; let owner: String?; let purchaseDate: String?
    let location: String?; let unopenedExpirationDate: String?; let openedExpirationDate: String?; let openedDate: String?
}

enum RecipeCategory: String, Codable, CaseIterable, Identifiable {
    case breakfast, meatDish = "meat_dish", vegetableDish = "vegetable_dish", aquatic, soup, staple
    case semiFinished = "semi-finished", dessert, drink, condiment
    var id: String { rawValue }
    var title: String {
        switch self {
        case .breakfast: "早餐"; case .meatDish: "肉类"; case .vegetableDish: "蔬菜"
        case .aquatic: "水产"; case .soup: "汤"; case .staple: "主食"
        case .semiFinished: "半成品"; case .dessert: "甜点"; case .drink: "饮品"; case .condiment: "调味品"
        }
    }
}

struct Ingredient: Codable, Hashable, Identifiable {
    var ingredientName: String
    var normalizedName: String?
    var quantity: String?
    var unit: String?
    var isOptional = false
    var isSeasoning = false
    var sortOrder = 0
    var id: String { "\(sortOrder)-\(ingredientName)" }

    enum CodingKeys: String, CodingKey { case ingredientName, normalizedName, quantity, unit, isOptional, isSeasoning, sortOrder }
    init(ingredientName: String, normalizedName: String? = nil, quantity: String? = nil, unit: String? = nil, isOptional: Bool = false, isSeasoning: Bool = false, sortOrder: Int = 0) {
        self.ingredientName = ingredientName; self.normalizedName = normalizedName; self.quantity = quantity; self.unit = unit
        self.isOptional = isOptional; self.isSeasoning = isSeasoning; self.sortOrder = sortOrder
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        ingredientName = try values.decode(String.self, forKey: .ingredientName)
        normalizedName = try values.decodeIfPresent(String.self, forKey: .normalizedName)
        quantity = try values.decodeIfPresent(String.self, forKey: .quantity); unit = try values.decodeIfPresent(String.self, forKey: .unit)
        isOptional = try values.decodeIfPresent(Bool.self, forKey: .isOptional) ?? false
        isSeasoning = try values.decodeIfPresent(Bool.self, forKey: .isSeasoning) ?? false
        sortOrder = try values.decodeIfPresent(Int.self, forKey: .sortOrder) ?? 0
    }
}
struct RecipeStep: Codable, Hashable, Identifiable {
    var stepNumber: Int; var instruction: String
    var id: Int { stepNumber }

    enum CodingKeys: String, CodingKey { case stepNumber, instruction }
    init(stepNumber: Int, instruction: String) { self.stepNumber = stepNumber; self.instruction = instruction }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        stepNumber = try values.decodeIfPresent(Int.self, forKey: .stepNumber) ?? 0
        instruction = try values.decodeIfPresent(String.self, forKey: .instruction) ?? ""
    }
}
struct RecipeSummary: Codable, Identifiable, Hashable {
    let id: Int; let sourceType: String; let sourceName: String; let title: String
    let category: String?; let difficulty: String?; let cookTimeMinutes: Int?
    let isUserCreated: Bool; let baseRecipeId: Int?; var isFavorite: Bool; let hasBeenCooked: Bool
    let createdAt: String?
}
struct Recipe: Codable, Identifiable, Hashable {
    let id: Int; let sourceType: String; let sourceName: String; let sourceUrl: String?; let sourcePath: String?
    let licenseName: String?; var title: String; var category: String?; var description: String?
    var difficulty: String?; var servings: String?; var cookTimeMinutes: Int?; var rawMarkdown: String?
    let isUserCreated: Bool; let baseRecipeId: Int?; var isFavorite: Bool; let hasBeenCooked: Bool
    var ingredients: [Ingredient]; var steps: [RecipeStep]; let createdAt: String?; let updatedAt: String?
}
struct RecipeWrite: Encodable {
    let title: String; let category: RecipeCategory; let description: String?; let difficulty: String?
    let servings: String?; let cookTimeMinutes: Int?; let rawMarkdown: String?
    let ingredients: [Ingredient]; let steps: [RecipeStep]

    enum CodingKeys: String, CodingKey { case title, category, description, difficulty, servings, cookTimeMinutes, rawMarkdown, ingredients, steps }
    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(title, forKey: .title); try values.encode(category, forKey: .category)
        try values.encode(description, forKey: .description); try values.encode(difficulty, forKey: .difficulty)
        try values.encode(servings, forKey: .servings); try values.encode(cookTimeMinutes, forKey: .cookTimeMinutes)
        try values.encode(rawMarkdown, forKey: .rawMarkdown); try values.encode(ingredients, forKey: .ingredients); try values.encode(steps, forKey: .steps)
    }
}

struct RecipeRecommendation: Codable, Identifiable, Hashable {
    let recipeId: Int; let title: String; let score: Double; let reason: String?
    let matchedInventoryItems: [String]; let expiringInventoryItems: [String]; let missingIngredients: [String]
    let isFavorite: Bool; let isNewSuggestion: Bool; let sourceType: String
    var id: Int { recipeId }
}
struct RecommendationResponse: Codable, Hashable { let sourceNotice: String; let recommendations: [RecipeRecommendation] }
struct SourceInfo: Codable, Hashable, Identifiable { let name: String; let url: String; let license: String; let notice: String; var id: String { url } }

struct ConsumePreviewItem: Codable, Identifiable, Hashable {
    let ingredientName: String; let itemId: Int; let itemName: String
    let availableQuantity: Double; let availableUnit: String; let recipeQuantity: String?
    let suggestedQuantity: Double?; let unit: String; let needsUserInput: Bool
    let status: String; let currentExpirationDate: String?; let confidence: String
    var id: Int { itemId }
}
struct ConsumePreview: Codable, Hashable {
    let recipeId: Int; let title: String; let suggestions: [ConsumePreviewItem]; let unmatchedIngredients: [String]

    func consumption(selected: Set<Int>, amounts: [Int: String]) -> [CookConsumeItem]? {
        var items: [CookConsumeItem] = []
        var processed: Set<Int> = []
        for suggestion in suggestions where selected.contains(suggestion.itemId) {
            guard processed.insert(suggestion.itemId).inserted else { continue }
            guard let amount = amounts[suggestion.itemId]?.quantityValue(),
                  amount > 0, amount <= suggestion.availableQuantity else { return nil }
            items.append(.init(itemId: suggestion.itemId, quantity: amount, ingredientName: suggestion.ingredientName))
        }
        return items.count == selected.count ? items : nil
    }
}
struct CookConsumeItem: Encodable { let itemId: Int; let quantity: Double; let ingredientName: String }
struct CookRequest: Encodable { let consumeItems: [CookConsumeItem]; let notes: String? }
struct CookResultItem: Codable, Hashable { let itemId: Int; let itemName: String; let consumedQuantity: Double; let remainingQuantity: Double; let status: String }
struct CookResponse: Codable, Hashable { let message: String; let recipeId: Int; let title: String; let consumedItems: [CookResultItem]; let notes: String? }

struct ExplorePreferences: Encodable, Hashable {
    var inventoryItemIds: [Int] = []; var extraIngredients: [String] = []; var flavors: [String] = []
    var textures: [String] = []; var cuisineGroup: String?; var cuisine: String?; var cookingMethods: [String] = []
    var maxTimeMinutes: Int?; var difficulty: String?; var prioritizeExpiring = true; var allowMissingIngredients = true
}
struct ExploreRequest: Encodable { let mode: String; let structured: ExplorePreferences?; let naturalLanguage: String? }
struct ExploreIdea: Codable, Identifiable, Hashable {
    var ideaId: String; var title: String; var description: String?; var sourceType: String; var recipeId: Int?
    var matchedIngredients: [String]; var expiringIngredients: [String]; var missingIngredients: [String]
    var flavors: [String]; var textures: [String]; var cuisineGroup: String?; var cuisine: String?
    var cookingMethod: String?; var estimatedTimeMinutes: Int?; var reason: String?; var canExpandToRecipe: Bool
    var id: String { ideaId.isEmpty ? title : ideaId }

    var action: ExploreIdeaAction {
        if sourceType == "existing_recipe", let recipeId { return .openRecipe(recipeId) }
        return canExpandToRecipe ? .expand : .none
    }
}

enum ExploreIdeaAction: Equatable {
    case openRecipe(Int)
    case expand
    case none
}

struct AIWarning: Decodable, Hashable {
    let code: String
    let params: [String: String]
    let message: String?
    let detail: String?

    private enum CodingKeys: String, CodingKey { case code, params, message, detail }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        code = try values.decode(String.self, forKey: .code)
        params = (try? values.decodeIfPresent([String: String].self, forKey: .params)) ?? [:]
        message = try? values.decodeIfPresent(String.self, forKey: .message)
        detail = try? values.decodeIfPresent(String.self, forKey: .detail)
    }
}

struct ExploreResponse: Decodable, Hashable {
    let mode: String
    let inputMode: String
    let locale: String
    let ideas: [ExploreIdea]
    let warnings: [AIWarning]
}
struct ExpandRequest: Encodable { let idea: ExploreIdea }
struct ExpandResponse: Decodable {
    let recipeDraft: RecipeDraft
    let locale: String
    let warnings: [AIWarning]
}
struct RecipeDraft: Codable, Hashable {
    var title: String; var category: RecipeCategory?; var description: String?; var difficulty: String?
    var servings: String?; var cookTimeMinutes: Int?; var rawMarkdown: String?
    var ingredients: [Ingredient]; var steps: [RecipeStep]

    enum CodingKeys: String, CodingKey { case title, category, description, difficulty, servings, cookTimeMinutes, rawMarkdown, ingredients, steps }
    init(title: String, category: RecipeCategory?, description: String?, difficulty: String?, servings: String?, cookTimeMinutes: Int?, rawMarkdown: String?, ingredients: [Ingredient], steps: [RecipeStep]) {
        self.title = title; self.category = category; self.description = description; self.difficulty = difficulty
        self.servings = servings; self.cookTimeMinutes = cookTimeMinutes; self.rawMarkdown = rawMarkdown
        self.ingredients = ingredients; self.steps = steps
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        title = try values.decodeIfPresent(String.self, forKey: .title) ?? ""
        category = try? values.decodeIfPresent(RecipeCategory.self, forKey: .category)
        description = try values.decodeIfPresent(String.self, forKey: .description)
        difficulty = try values.decodeIfPresent(String.self, forKey: .difficulty)
        servings = try values.decodeIfPresent(String.self, forKey: .servings)
        cookTimeMinutes = try values.decodeIfPresent(Int.self, forKey: .cookTimeMinutes)
        rawMarkdown = try values.decodeIfPresent(String.self, forKey: .rawMarkdown)
        ingredients = try values.decodeIfPresent([Ingredient].self, forKey: .ingredients) ?? []
        steps = try values.decodeIfPresent([RecipeStep].self, forKey: .steps) ?? []
        for index in steps.indices where steps[index].stepNumber <= 0 { steps[index].stepNumber = index + 1 }
    }
}

enum API {
    static let formatter: DateFormatter = {
        let value = DateFormatter(); value.calendar = .init(identifier: .gregorian)
        value.locale = .init(identifier: "en_US_POSIX"); value.dateFormat = "yyyy-MM-dd"; return value
    }()
    static func date(_ string: String?) -> Date? { string.flatMap(formatter.date) }
    static func string(_ date: Date) -> String { formatter.string(from: date) }
}
