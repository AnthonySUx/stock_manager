#if DEBUG
import SwiftUI

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
        _intake = State(initialValue: IntakeStore(client: client, inventory: inventory, restock: RestockStore(client: client)))
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
            let enabled = !ProcessInfo.processInfo.arguments.contains("-ui-testing-intake-unavailable")
            return (200, #"{"ai":{"text":\#(enabled),"vision":false,"asr":false}}"#)
        case ("GET", "/api/items"):
            return (200, "[]")
        case ("GET", "/api/restock"):
            return (200, #"[{"id":7,"name":"牛奶","status":"pending"}]"#)
        case ("GET", "/api/categories"), ("GET", "/api/categories/flat"):
            return (200, Self.categories)
        case ("POST", "/api/intake/parse"):
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

    private static let confirmed = """
    {"created":[{"temporary_id":"cand_1a2b3c4d","item_id":41},{"temporary_id":"cand_12345678","item_id":42},
      {"temporary_id":"cand_00000001","item_id":43}],"restock_done":[],"restock_partial":[],
      "warnings":[{"code":"restock_already_done","params":{"restock_id":"7"}}]}
    """
}
#endif
