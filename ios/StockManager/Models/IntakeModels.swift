import Foundation

struct IntakeSource: Decodable, Equatable {
    let inputKind: String
    var imageIndex: Int?
    var span: String?
}

struct IntakeReceiptSuggestion: Decodable, Equatable {
    let name: String
    let source: String
    let confirmedCount: Int
}

struct IntakeCandidate: Codable, Equatable, Identifiable {
    // A string-keyed dictionary retains wire keys, explicit nulls and future metadata.
    private var fields: [String: JSONValue]
    let temporaryId: String
    let confidence: Double
    let source: IntakeSource

    var id: String { temporaryId }
    var name: String? { get { self[text: "name"] } set { self[text: "name"] = newValue } }
    var quantityValue: Double? {
        get { fields["quantity_value"]?.intakeNumber }
        set { fields["quantity_value"] = newValue.map(JSONValue.number) ?? .null }
    }
    var quantityUnit: String? { get { self[text: "quantity_unit"] } set { self[text: "quantity_unit"] = newValue } }
    var categoryId: Int? { get { self[integer: "category_id"] } set { self[integer: "category_id"] = newValue } }
    var owner: String? { get { self[text: "owner"] } set { self[text: "owner"] = newValue } }
    var location: String? { get { self[text: "location"] } set { self[text: "location"] = newValue } }
    var purchaseDate: String? { get { self[text: "purchase_date"] } set { self[text: "purchase_date"] = newValue } }
    var unopenedExpirationDate: String? {
        get { self[text: "unopened_expiration_date"] }
        set {
            self[text: "unopened_expiration_date"] = newValue
            self[text: "expiration_source"] = newValue?.nilIfBlank == nil ? "none" : "stated"
        }
    }
    var suggestedUnopenedExpirationDate: String? { self[text: "suggested_unopened_expiration_date"] }
    var expirationSource: String { self[text: "expiration_source"] ?? "none" }
    var openedExpirationDate: String? {
        get { self[text: "opened_expiration_date"] }
        set { self[text: "opened_expiration_date"] = newValue }
    }
    var openedDate: String? { get { self[text: "opened_date"] } set { self[text: "opened_date"] = newValue } }
    var notes: String? { get { self[text: "notes"] } set { self[text: "notes"] = newValue } }
    var matchedRestockId: Int? { self[integer: "matched_restock_id"] }
    var restockAction: String? { self[text: "restock_action"] }
    var fieldConfidence: [String: Double] {
        guard case .object(let values) = fields["field_confidence"] else { return [:] }
        return values.compactMapValues(\.intakeNumber)
    }
    var warnings: [AIWarning] { (try? Self.decodeField(fields["warnings"])) ?? [] }
    var rawName: String? { self[text: "raw_name"] }
    var genericName: String? { self[text: "generic_name"] }
    var storeName: String? { self[text: "store_name"] }
    var price: Double? { fields["price"]?.intakeNumber }
    var specificity: String? { self[text: "specificity"] }
    var aliasMode: String? { self[text: "alias_mode"] }
    var autoApplyAllowed: Bool? { fields["auto_apply_allowed"]?.intakeBool }
    var requiresUserReview: Bool? { fields["requires_user_review"]?.intakeBool }
    var reviewReason: String? { self[text: "review_reason"] }
    var matchMethod: String? { self[text: "match_method"] }
    var suggestions: [IntakeReceiptSuggestion]? { try? Self.decodeField(fields["suggestions"]) }

    var invalidDraftFields: [String] {
        var invalid: [String] = []
        if !allows("quantity_value", when: { $0.intakeNumber.map { $0.isFinite && $0 > 0 } == true }) {
            invalid.append("quantity_value")
        }
        if !allows("category_id", when: { $0.intakeInteger.map { $0 > 0 } == true }) {
            invalid.append("category_id")
        }
        for key in ["purchase_date", "suggested_unopened_expiration_date", "opened_expiration_date", "opened_date",
                    "unopened_expiration_date"] {
            if !allows(key, when: { value in
                guard let date = value.intakeString else { return false }
                return (key == "unopened_expiration_date" && date == "infinite") || Self.isValidDate(date)
            }) {
                invalid.append(key)
            }
        }
        for (key, limit) in [("name", 255), ("raw_name", 255), ("quantity_unit", 50), ("owner", 100), ("location", 100)] {
            if !allows(key, when: { $0.intakeString.map { $0.unicodeScalars.count <= limit } == true }) {
                invalid.append(key)
            }
        }
        return invalid
    }

    private func allows(_ key: String, when valid: (JSONValue) -> Bool) -> Bool {
        guard let value = fields[key], value != .null else { return true }
        return valid(value)
    }

    private static let dateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = .withFullDate
        formatter.timeZone = .gmt
        return formatter
    }()

    private static func isValidDate(_ value: String) -> Bool {
        dateFormatter.date(from: value).map(dateFormatter.string(from:)) == value
    }

    init(from decoder: Decoder) throws {
        try self.init(fields: decoder.singleValueContainer().decode([String: JSONValue].self))
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(fields)
    }

    private init(fields: [String: JSONValue]) throws {
        guard let temporaryId = fields["temporary_id"]?.intakeString,
              let confidence = fields["confidence"]?.intakeNumber,
              let source: IntakeSource = try Self.decodeField(fields["source"]) else {
            throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "Incomplete intake candidate"))
        }
        self.init(fields: fields, temporaryId: temporaryId, confidence: confidence, source: source)
    }

    private init(fields: [String: JSONValue], temporaryId: String, confidence: Double, source: IntakeSource) {
        self.fields = fields
        self.temporaryId = temporaryId
        self.confidence = confidence
        self.source = source
    }

    static func manual(temporaryId: String) -> Self {
        let source = IntakeSource(inputKind: "text")
        return Self(fields: ["temporary_id": .string(temporaryId), "confidence": .integer(1),
                             "source": .object(["input_kind": .string(source.inputKind)])],
                    temporaryId: temporaryId, confidence: 1, source: source)
    }

    func applying(_ changes: [String: JSONValue]) throws -> Self {
        var merged = fields.merging(changes) { _, changed in changed }
        merged["temporary_id"] = .string(temporaryId)
        return try Self(fields: merged)
    }

    func offsettingImageIndex(by offset: Int) throws -> Self {
        guard offset > 0, let index = source.imageIndex, index >= 0, index < Int.max - offset,
              case .object(var metadata) = fields["source"] else { return self }
        metadata["image_index"] = .integer(index + offset)
        return try applying(["source": .object(metadata)])
    }

    mutating func adoptSuggestedExpiration() {
        guard let suggestion = suggestedUnopenedExpirationDate else { return }
        unopenedExpirationDate = suggestion
    }

    mutating func removeRestockLink() {
        self[integer: "matched_restock_id"] = nil
        self[text: "restock_action"] = nil
    }

    private subscript(text key: String) -> String? {
        get { fields[key]?.intakeString }
        set { fields[key] = newValue.map(JSONValue.string) ?? .null }
    }

    private subscript(integer key: String) -> Int? {
        get { fields[key]?.intakeInteger }
        set { fields[key] = newValue.map(JSONValue.integer) ?? .null }
    }

    private static func decodeField<T: Decodable>(_ value: JSONValue?) throws -> T? {
        guard let value, value != .null else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: JSONEncoder().encode(value))
    }
}

private extension JSONValue {
    var intakeString: String? {
        if case .string(let value) = self { value } else { nil }
    }
    var intakeInteger: Int? {
        if case .integer(let value) = self { value } else { nil }
    }
    var intakeBool: Bool? {
        if case .bool(let value) = self { value } else { nil }
    }
    var intakeNumber: Double? {
        switch self {
        case .number(let value): value
        case .integer(let value): Double(value)
        default: nil
        }
    }
}

struct IntakeClarification: Equatable {
    let temporaryIds: [String]
    let questionCode: String
    let question: String
    let source: IntakeSource?
}

enum IntakeOperation: Decodable, Equatable {
    case add(IntakeCandidate, source: IntakeSource?)
    case update(temporaryId: String, changes: [String: JSONValue], source: IntakeSource?)
    case delete(temporaryId: String, reasonCode: String, source: IntakeSource?)
    case clarify(IntakeClarification)
    case unknown(String)

    private enum CodingKeys: String, CodingKey {
        case op, candidate, temporaryId, changes, reasonCode, temporaryIds, questionCode, question, source
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        let op = try values.decode(String.self, forKey: .op)
        let source = try? values.decodeIfPresent(IntakeSource.self, forKey: .source)
        switch op {
        case "add":
            self = .add(try values.decode(IntakeCandidate.self, forKey: .candidate), source: source)
        case "update":
            self = .update(temporaryId: try values.decode(String.self, forKey: .temporaryId),
                           changes: try values.decode([String: JSONValue].self, forKey: .changes), source: source)
        case "delete":
            self = .delete(temporaryId: try values.decode(String.self, forKey: .temporaryId),
                           reasonCode: try values.decode(String.self, forKey: .reasonCode), source: source)
        case "clarify":
            self = .clarify(.init(temporaryIds: try values.decode([String].self, forKey: .temporaryIds),
                                  questionCode: try values.decode(String.self, forKey: .questionCode),
                                  question: try values.decode(String.self, forKey: .question), source: source))
        default:
            self = .unknown(op)
        }
    }
}

struct IntakeDraft: Encodable {
    let items: [IntakeCandidate]
}

struct IntakeContext: Encodable {
    var locale: String?
    var timezone: String?
    var purchaseDate: String?
}

struct IntakeParseRequest: Encodable {
    struct Input: Encodable {
        let type = "text"
        let text: String
    }

    let input: Input
    let draft: IntakeDraft
    let context: IntakeContext
}

struct IntakeParseResponse: Decodable {
    let operations: [IntakeOperation]
    let unparsedFragments: [String]
    let locale: String
    let warnings: [AIWarning]
}

struct IntakeConfirmDefaults: Encodable, Equatable {
    var owner: String?
    var location: String?

    var normalized: Self { .init(owner: owner?.nilIfBlank, location: location?.nilIfBlank) }
}

struct IntakeConfirmItem: Encodable {
    let temporaryId: String
    let name: String?
    let categoryId: Int?
    let quantityValue: Double?
    let quantityUnit: String?
    let purchaseDate: String?
    let unopenedExpirationDate: String?
    let openedExpirationDate: String?
    let openedDate: String?
    let owner: String?
    let location: String?
    let notes: String?
    let rawName: String?
    let storeName: String?
    let specificity: String?
    let matchedRestockId: Int?
    let restockAction: String?

    init(candidate: IntakeCandidate) {
        temporaryId = candidate.temporaryId
        name = candidate.name?.nilIfBlank
        categoryId = candidate.categoryId
        quantityValue = candidate.quantityValue
        quantityUnit = candidate.quantityUnit?.nilIfBlank
        purchaseDate = candidate.purchaseDate?.nilIfBlank
        unopenedExpirationDate = candidate.unopenedExpirationDate?.nilIfBlank
        openedExpirationDate = candidate.openedExpirationDate?.nilIfBlank
        openedDate = candidate.openedDate?.nilIfBlank
        owner = candidate.owner?.nilIfBlank
        location = candidate.location?.nilIfBlank
        notes = candidate.notes?.nilIfBlank
        rawName = candidate.rawName
        storeName = candidate.storeName
        specificity = candidate.specificity
        matchedRestockId = candidate.matchedRestockId
        restockAction = candidate.restockAction.flatMap { ["done", "partial", "none"].contains($0) ? $0 : nil }
    }
}

struct IntakeConfirmRequest: Encodable {
    let defaults: IntakeConfirmDefaults
    let items: [IntakeConfirmItem]
}

struct IntakeConfirmResponse: Decodable, Equatable {
    struct Created: Decodable, Equatable {
        let temporaryId: String
        let itemId: Int
    }

    let created: [Created]
    let restockDone: [Int]
    let restockPartial: [Int]
    let warnings: [AIWarning]
}
