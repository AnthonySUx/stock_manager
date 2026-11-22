import Foundation

struct APIErrorBody: Decodable {
    let code: String?
    let params: [String: JSONValue]?
    let detail: DetailValue?

    private enum CodingKeys: String, CodingKey { case code, params, detail }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        // Keep useful fields even if the server sends one field in an unexpected form.
        code = try? values.decodeIfPresent(String.self, forKey: .code)
        params = try? values.decodeIfPresent([String: JSONValue].self, forKey: .params)
        detail = try? values.decodeIfPresent(DetailValue.self, forKey: .detail)
    }
}

enum DetailValue: Decodable {
    case text(String)
    case validation([ValidationIssue])

    struct ValidationIssue: Decodable {
        let loc: [JSONValue]?
        let msg: String?

        var message: String {
            let location = loc?.compactMap(\.text).joined(separator: ".")
            return [location, msg].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "：")
        }
    }

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if let text = try? value.decode(String.self) { self = .text(text) }
        else { self = .validation(try value.decode([ValidationIssue].self)) }
    }

    var message: String? {
        let text = switch self {
        case .text(let text): text
        case .validation(let issues): issues.map(\.message).filter { !$0.isEmpty }.joined(separator: "\n")
        }
        return text.isEmpty ? nil : text
    }
}
