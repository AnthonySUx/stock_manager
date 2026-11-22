#if DEBUG
import SwiftUI

struct HouseholdSettingsUITestHost: View {
    @State private var inventory: InventoryStore
    @State private var categories: CategoryStore

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HouseholdSettingsUITestProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.test/api")!, token: "test-token",
                               session: URLSession(configuration: configuration))
        _inventory = State(initialValue: InventoryStore(client: client))
        _categories = State(initialValue: CategoryStore(client: client))
    }

    var body: some View {
        NavigationStack { SettingsView() }
            .environment(inventory)
            .environment(categories)
    }
}

private final class HouseholdSettingsUITestProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        let (status, body): (Int, String)
        switch (request.httpMethod, url.path) {
        case ("GET", "/api/settings"):
            (status, body) = (200, #"{"expiration_reminder_days":"3","default_locale":"ja","default_timezone":"Asia/Tokyo"}"#)
        case ("PATCH", "/api/settings"):
            (status, body) = (422, #"{"detail":"时区设置未通过验证"}"#)
        case ("GET", "/api/recipes/sources"):
            (status, body) = (200, "[]")
        case ("GET", "/api/categories"), ("GET", "/api/categories/flat"):
            (status, body) = (200, #" [ {"id":7,"name":"蔬菜","slug":"vegetables","recipe_usage":"always","is_system":true,"sort_order":0,"default_shelf_life_days":7} ] "#)
        default:
            (status, body) = (404, #"{"detail":"Unexpected UI test request"}"#)
        }
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
#endif
