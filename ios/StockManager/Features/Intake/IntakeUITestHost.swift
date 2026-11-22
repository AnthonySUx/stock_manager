#if DEBUG
import SwiftUI
import UIKit

struct IntakeUITestHost: View {
    @State private var inventory: InventoryStore
    @State private var categories: CategoryStore
    @State private var intake: IntakeStore
    @State private var capabilities = CapabilitiesStore()

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [IntakeUITestProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.test/api")!, token: "test-token",
                               session: URLSession(configuration: configuration))
        let inventory = InventoryStore(client: client)
        _inventory = State(initialValue: inventory)
        _categories = State(initialValue: CategoryStore(client: client))
        var candidates: [IntakeCandidate] = []
        if ProcessInfo.processInfo.arguments.contains("-ui-testing-intake-existing-draft") {
            var milk = IntakeCandidate.manual(temporaryId: "cand_1a2b3c4d")
            milk.name = "牛奶"
            milk.categoryId = 12
            milk.quantityValue = 2
            milk.quantityUnit = "瓶"
            milk.unopenedExpirationDate = "2026-11-27"
            if ProcessInfo.processInfo.arguments.contains("-ui-testing-intake-invalid-date") {
                milk.purchaseDate = "2026-13-40"
            }
            milk.owner = "小林"
            milk.location = "冰箱"
            candidates.append(milk)
        }
        _intake = State(initialValue: IntakeStore(client: client, inventory: inventory,
                                               restock: RestockStore(client: client), candidates: candidates))
    }

    static var photoFixtures: [Data]? {
        guard ProcessInfo.processInfo.arguments.contains("-ui-testing-intake-photo-fixtures") else { return nil }
        return [UIColor.white, .systemYellow].map { color in
            UIGraphicsImageRenderer(size: CGSize(width: 64, height: 96)).pngData { context in
                context.cgContext.setFillColor(color.cgColor)
                context.cgContext.fill(CGRect(x: 0, y: 0, width: 64, height: 96))
            }
        }
    }

    var body: some View {
        NavigationStack { InventoryListView() }
            .environment(inventory)
            .environment(categories)
            .environment(intake)
            .environment(capabilities)
            .task { await capabilities.refresh(using: inventory.client) }
    }
}

private final class IntakeUITestProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        let (status, body) = response(path: url.path)
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    private func response(path: String) -> (Int, String) {
        switch (request.httpMethod, path) {
        case ("GET", "/api/capabilities"):
            let arguments = ProcessInfo.processInfo.arguments
            let vision = arguments.contains("-ui-testing-intake-vision")
            let text = !vision && !arguments.contains("-ui-testing-intake-unavailable")
            let asr = arguments.contains("-ui-testing-asr")
            return (200, #"{"ai":{"text":\#(text),"vision":\#(vision),"asr":\#(asr)}}"#)
        case ("POST", "/api/speech/transcribe"):
            return (200, #"{"transcript":"两瓶牛奶","duration_ms":3000}"#)
        case ("GET", "/api/items"):
            return (200, "[]")
        case ("GET", "/api/restock"):
            return (200, #"[{"id":7,"name":"牛奶","status":"pending"}]"#)
        case ("GET", "/api/categories"), ("GET", "/api/categories/flat"):
            return (200, Self.categories)
        case ("POST", "/api/intake/parse"):
            if request.value(forHTTPHeaderField: "Content-Type")?.hasPrefix("multipart/form-data;") == true {
                return (200, Self.parsedPhotos)
            }
            let body = requestBody()
            let draft = body["draft"] as? [String: Any]
            guard let items = draft?["items"] as? [[String: Any]] else {
                return (400, #"{"detail":"缺少测试草稿"}"#)
            }
            if items.isEmpty { return (200, Self.parsed) }
            guard items.first(where: { $0["temporary_id"] as? String == "cand_1a2b3c4d" })?["purchase_date"] is NSNull else {
                return (400, #"{"detail":"购买日期应编码为 null"}"#)
            }
            return (200, #"{"operations":[],"unparsed_fragments":["已用清空购买日期的草稿重新解析"],"locale":"zh-CN","warnings":[]}"#)
        case ("POST", "/api/intake/confirm"):
            if ProcessInfo.processInfo.arguments.contains("-ui-testing-intake-vision") {
                let items = requestBody()["items"] as? [[String: Any]]
                guard let receipt = items?.first(where: { $0["temporary_id"] as? String == "cand_53c03b01" }),
                      receipt["name"] as? String == "Whole milk", receipt["raw_name"] as? String == "牛乳900",
                      receipt["store_name"] as? String == "超市", receipt["specificity"] as? String == "unknown" else {
                    return (422, #"{"detail":"Expected a reviewed receipt line with its original metadata"}"#)
                }
                return (201, #"{"created":[{"temporary_id":"cand_53c03b01","item_id":41},{"temporary_id":"cand_53c03b02","item_id":42}],"restock_done":[],"restock_partial":[],"warnings":[]}"#)
            }
            if ProcessInfo.processInfo.arguments.contains("-ui-testing-intake-existing-draft") {
                return (201, #"{"created":[{"temporary_id":"cand_1a2b3c4d","item_id":41}],"restock_done":[],"restock_partial":[],"warnings":[]}"#)
            }
            return (201, Self.confirmed)
        default:
            return (404, #"{"detail":"Unexpected intake UI test request"}"#)
        }
    }

    private func requestBody() -> [String: Any] {
        var data = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 1024)
            var count = stream.read(&buffer, maxLength: buffer.count)
            while count > 0 {
                data.append(contentsOf: buffer.prefix(count))
                count = stream.read(&buffer, maxLength: buffer.count)
            }
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    private static let categories = """
    [{"id":12,"name":"食品","slug":"food","recipe_usage":"always","is_system":true,"sort_order":0}]
    """

    private static let parsed = """
    {
      "operations": [
        {"op":"add","candidate":{"temporary_id":"cand_1a2b3c4d","name":"牛奶",
         "quantity_value":2,"quantity_unit":"瓶","category_id":12,"purchase_date":"2026-11-20",
         "suggested_unopened_expiration_date":"2026-11-27","expiration_source":"estimated",
         "confidence":0.55,"warnings":[{"code":"expiration_date_inferred","params":{"basis":"category_default"}}],
         "source":{"input_kind":"text"},"owner":"小林","location":"冰箱","matched_restock_id":7,"restock_action":"done"}},
        {"op":"add","candidate":{"temporary_id":"cand_12345678","name":"五花肉",
         "quantity_value":2,"quantity_unit":"斤","category_id":12,"unopened_expiration_date":"2026-11-25",
         "confidence":0.95,"source":{"input_kind":"text"},"owner":"小林","location":"冰箱"}},
        {"op":"add","candidate":{"temporary_id":"cand_00000001","name":"鸡蛋",
         "quantity_value":1,"quantity_unit":"盒","category_id":12,"unopened_expiration_date":"2026-11-30",
         "confidence":0.95,"source":{"input_kind":"text"},"owner":"小林","location":"冰箱"}}
      ],
      "unparsed_fragments":[],"locale":"zh-CN","warnings":[]
    }
    """

    private static let parsedPhotos = """
    {
      "operations": [
        {"op":"add","candidate":{"temporary_id":"cand_53c03b01","name":null,
         "raw_name":"牛乳900","generic_name":"牛奶","store_name":"超市","specificity":"unknown",
         "requires_user_review":true,"suggestions":[{"name":"Whole milk","source":"user_alias_history","confirmed_count":2}],
         "quantity_value":1,"quantity_unit":"瓶","category_id":12,"unopened_expiration_date":"2026-11-27",
         "confidence":0.5,"source":{"input_kind":"receipt","image_index":0},"owner":"小林","location":"冰箱"}},
        {"op":"add","candidate":{"temporary_id":"cand_53c03b02","name":"鸡蛋",
         "quantity_value":1,"quantity_unit":"盒","category_id":12,"unopened_expiration_date":"2026-11-30",
         "expiration_source":"printed","confidence":0.95,"source":{"input_kind":"product_closeup","image_index":1},
         "owner":"小林","location":"冰箱"}}
      ],
      "unparsed_fragments":[],"locale":"zh-CN","warnings":[]
    }
    """

    private static let confirmed = """
    {"created":[{"temporary_id":"cand_1a2b3c4d","item_id":41},{"temporary_id":"cand_12345678","item_id":42},
      {"temporary_id":"cand_00000001","item_id":43}],"restock_done":[],"restock_partial":[],
      "warnings":[{"code":"restock_already_done","params":{"restock_id":"7"}}]}
    """
}
#endif
