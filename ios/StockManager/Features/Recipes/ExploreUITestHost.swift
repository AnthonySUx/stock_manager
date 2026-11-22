#if DEBUG
import SwiftUI

struct ExploreUITestHost: View {
    @State private var inventory: InventoryStore
    @State private var recipes: RecipeStore
    @State private var capabilities = CapabilitiesStore()

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ExploreUITestProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.test/api")!, token: "test-token",
                               session: URLSession(configuration: configuration))
        _inventory = State(initialValue: InventoryStore(client: client))
        _recipes = State(initialValue: RecipeStore(client: client))
    }

    var body: some View {
        NavigationStack { RecipeLibraryView() }
            .environment(inventory)
            .environment(recipes)
            .environment(capabilities)
            .task { await capabilities.refresh(using: recipes.client) }
    }
}

enum ExploreTestFixtures {
    // The Explore envelope follows recipes.md's done event and ideas[] field table.
    static let explore = """
    {
      "mode": "ai", "input_mode": "natural_language", "locale": "zh-CN",
      "ideas": [
        {
          "idea_id": "3f2a9c1b", "title": "番茄炒蛋", "source_type": "existing_recipe", "recipe_id": 42,
          "matched_ingredients": ["番茄", "鸡蛋"], "expiring_ingredients": [], "missing_ingredients": [],
          "flavors": [], "textures": [], "cuisine_group": "chinese", "cooking_method": "stir_fry",
          "estimated_time_minutes": 15, "can_expand_to_recipe": false
        },
        {
          "idea_id": "8d0e4b77", "title": "红烧豆腐", "source_type": "ai_idea",
          "matched_ingredients": ["豆腐"], "expiring_ingredients": [], "missing_ingredients": [],
          "flavors": [], "textures": [], "cuisine_group": "chinese", "cooking_method": "braise",
          "estimated_time_minutes": 20, "can_expand_to_recipe": true
        }
      ],
      "warnings": [{"code": "idea_dropped_wrong_language", "params": {"title": "Tomato soup"}}]
    }
    """

    // Response example from recipes.md, Expand Idea to Draft.
    static let expand = """
    {
      "locale": "zh-CN",
      "recipe_draft": {
        "title": "番茄炒蛋", "category": "vegetable_dish", "description": "…",
        "difficulty": "easy", "servings": "2", "cook_time_minutes": 15, "raw_markdown": null,
        "ingredients": [{"ingredient_name": "番茄", "normalized_name": null, "quantity": "2",
                         "unit": "个", "is_optional": false, "is_seasoning": false, "sort_order": 0}],
        "steps": [{"step_number": 1, "instruction": "…"}]
      },
      "warnings": [{"code": "draft_ai_generated", "params": {}}]
    }
    """
}

private final class ExploreUITestProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        let (status, body): (Int, String)
        var isStream = false
        var holdOpen = false
        switch (request.httpMethod, url.path) {
        case ("GET", "/api/capabilities"):
            let enabled = !ProcessInfo.processInfo.arguments.contains("-ui-testing-explore-unavailable")
            let asr = ProcessInfo.processInfo.arguments.contains("-ui-testing-asr")
            (status, body) = (200, #"{"ai":{"text":\#(enabled),"vision":false,"asr":\#(asr)}}"#)
        case ("POST", "/api/speech/transcribe"):
            (status, body) = (200, #"{"transcript":"找一道牛奶和鸡蛋的晚餐","duration_ms":3000}"#)
        case ("GET", "/api/items"), ("GET", "/api/recipes"):
            (status, body) = (200, "[]")
        case ("POST", "/api/recipes/explore/stream"):
            isStream = true
            holdOpen = ProcessInfo.processInfo.arguments.contains("-ui-testing-explore-stream-progress")
            do {
                (status, body) = (200, try Self.streamBody(holdOpen: holdOpen))
            } catch {
                client?.urlProtocol(self, didFailWithError: error)
                return
            }
        case ("POST", "/api/recipes/explore/expand"):
            (status, body) = (200, ExploreTestFixtures.expand
                .replacingOccurrences(of: "番茄炒蛋", with: "红烧豆腐")
                .replacingOccurrences(of: "番茄", with: "豆腐"))
        case ("GET", "/api/recipes/42"):
            (status, body) = (200, Self.recipe(id: 42, title: "番茄炒蛋", source: "菜谱库测试来源"))
        case ("POST", "/api/recipes"):
            (status, body) = (201, Self.recipe(id: 43, title: "红烧豆腐", source: "我的菜谱"))
        default:
            (status, body) = (404, #"{"detail":"Unexpected UI test request"}"#)
        }
        let mimeType = isStream ? "text/event-stream" : "application/json"
        guard let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil,
                                             headerFields: ["Content-Type": mimeType]) else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        if !holdOpen { client?.urlProtocolDidFinishLoading(self) }
    }

    override func stopLoading() {}

    private static func streamBody(holdOpen: Bool) throws -> String {
        guard var summary = try JSONSerialization.jsonObject(with: Data(ExploreTestFixtures.explore.utf8)) as? [String: Any],
              let ideas = summary.removeValue(forKey: "ideas") as? [[String: Any]] else {
            throw URLError(.cannotDecodeContentData)
        }
        let events = try (holdOpen ? ideas.prefix(1) : ideas[...]).map { try event("idea", value: $0) }.joined()
        if holdOpen { return events }
        summary["count"] = ideas.count
        return events + (try event("done", value: summary))
    }

    private static func event(_ name: String, value: [String: Any]) throws -> String {
        let json = try JSONSerialization.data(withJSONObject: value)
        return "event: \(name)\ndata: \(String(decoding: json, as: UTF8.self))\n\n"
    }

    private static func recipe(id: Int, title: String, source: String) -> String {
        """
        {"id":\(id),"source_type":"user","source_name":"\(source)","title":"\(title)",
         "category":"vegetable_dish","difficulty":"easy","is_user_created":true,"is_favorite":false,
         "has_been_cooked":false,"ingredients":[],"steps":[]}
        """
    }
}
#endif
