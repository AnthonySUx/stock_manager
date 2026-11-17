import XCTest
@testable import StockManager

final class APIContractTests: XCTestCase {
    func testQuantityInputAcceptsLocalizedAndFullWidthNumbers() {
        XCTAssertEqual("1.5".quantityValue(locale: Locale(identifier: "en_US")), 1.5)
        XCTAssertEqual("1,5".quantityValue(locale: Locale(identifier: "de_DE")), 1.5)
        XCTAssertEqual("１．５".quantityValue(locale: Locale(identifier: "zh_CN")), 1.5)
        XCTAssertNil("1.2.3".quantityValue())
        XCTAssertNil("一份".quantityValue())
    }

    func testRecommendationEmptyReasonDistinguishesMissingRecipes() {
        let noRecipes = RecommendationSnapshot(recommendations: [], hasRecipes: false, eligibleInventoryCount: 2)
        XCTAssertTrue(noRecipes.emptyMessage.contains("菜谱库还是空的"))
        let noEligibleInventory = RecommendationSnapshot(recommendations: [], hasRecipes: true, eligibleInventoryCount: 0)
        XCTAssertTrue(noEligibleInventory.emptyMessage.contains("分类的菜谱用途"))
    }

    func testActionStateHasOneAuthoritativePhase() {
        XCTAssertFalse(ActionState.idle.isRunning)
        XCTAssertTrue(ActionState.running.isRunning)
        XCTAssertEqual(ActionState.failed("网络中断").errorMessage, "网络中断")
        XCTAssertNil(ActionState.succeeded(nil).errorMessage)
    }

    func testExpirationChoiceMapsToBackendContract() {
        XCTAssertEqual(ExpirationChoice.infinite.apiValue, "infinite")
        let date = Calendar(identifier: .gregorian).date(from: DateComponents(year: 2026, month: 11, day: 17))!
        XCTAssertEqual(ExpirationChoice.dated(date).apiValue, "2026-11-17")
    }

    func testRestockUsesTypedStatusAndFilter() throws {
        let data = #"{"id":3,"name":"牛奶","category_id":null,"quantity_value":1,"quantity_unit":"盒","status":"done","source_item_id":null,"notes":null}"#.data(using: .utf8)!
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertEqual(try decoder.decode(RestockItem.self, from: data).status, .done)
        XCTAssertEqual(RestockFilter.pending.apiValue, "pending")
        XCTAssertNil(RestockFilter.all.apiValue)
    }

    func testRecipeFiltersMapToBackendValues() {
        XCTAssertEqual(RecipeSourceFilter.aiSaved.rawValue, "ai_saved")
        XCTAssertEqual(RecommendationScene.dessertDrink.rawValue, "dessert_drink")
        XCTAssertNotEqual(PaginationState.loading, .ready)
    }

    func testItemDraftOpeningStateCannotContainOrphanedOpenDate() throws {
        let data = #"{"id":1,"name":"牛奶","category_id":7,"category":{"id":7,"name":"饮品","slug":"drink","parent_id":1,"recipe_usage":"conditional","is_system":true,"sort_order":2},"owner":"全家","purchase_date":"2026-11-16","quantity_value":2,"quantity_unit":"盒","location":"冰箱","unopened_expiration_date":"infinite","opened_expiration_date":"2026-11-19","opened_date":"2026-11-17","current_expiration_date":"2026-11-19","status":"active","notes":null}"#.data(using: .utf8)!
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let draft = ItemDraft(item: try decoder.decode(StockItem.self, from: data))
        XCTAssertEqual(draft.unopenedExpiration, .infinite)
        guard case .opened(_, .dated) = draft.opening else { return XCTFail("开封日期与开封后期限应属于同一状态") }
    }

    func testItemDecodesCurrentBackendContract() throws {
        let data = #"{"id":1,"name":"牛奶","category_id":7,"category":{"id":7,"name":"饮品","slug":"drink","parent_id":1,"recipe_usage":"conditional","is_system":true,"sort_order":2},"owner":"全家","purchase_date":"2026-11-16","quantity_value":2,"quantity_unit":"盒","location":"冰箱","unopened_expiration_date":"2026-11-20","opened_expiration_date":null,"opened_date":null,"current_expiration_date":"2026-11-20","status":"expiring soon","notes":null}"#.data(using: .utf8)!
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let item = try decoder.decode(StockItem.self, from: data)
        XCTAssertEqual(item.category.id, 7)
        XCTAssertEqual(item.category.recipeUsage, .conditional)
        XCTAssertEqual(item.status, .expiringSoon)
        XCTAssertEqual(item.quantityText, "2 盒")
    }

    func testMovingCategoryToTopEncodesExplicitNull() throws {
        let update = CategoryUpdate(name: "冷藏", parentId: nil, includeParentId: true, recipeUsage: .always, sortOrder: 3)
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(update)) as? [String: Any])
        XCTAssertTrue(object["parent_id"] is NSNull)
        XCTAssertEqual(object["recipe_usage"] as? String, "always")
    }

    func testItemUpdateCanExplicitlyClearNullableFields() throws {
        let update = ItemUpdate(name: "牛奶", categoryId: 1, owner: "全家", purchaseDate: "2026-11-16", quantityValue: 1,
            quantityUnit: "盒", location: "冰箱", unopenedExpirationDate: "infinite", openedExpirationDate: nil, openedDate: nil, notes: nil)
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(update)) as? [String: Any])
        XCTAssertTrue(object["opened_expiration_date"] is NSNull)
        XCTAssertTrue(object["opened_date"] is NSNull)
        XCTAssertTrue(object["notes"] is NSNull)
    }

    func testExploreDraftIngredientsAcceptBackendMinimalShape() throws {
        let data = #"{"ingredient_name":"番茄","quantity":"2","unit":"个"}"#.data(using: .utf8)!
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let ingredient = try decoder.decode(Ingredient.self, from: data)
        XCTAssertFalse(ingredient.isOptional)
        XCTAssertFalse(ingredient.isSeasoning)
        XCTAssertEqual(ingredient.sortOrder, 0)
    }

    func testExploreDraftToleratesMissingAIFields() throws {
        let data = #"{"recipe_draft":{"title":"早餐","category":"unknown","ingredients":[{"ingredient_name":"鸡蛋","quantity":"2","unit":"个"}],"steps":[{"instruction":"打散鸡蛋"}],"warnings":["请确认内容"]}}"#.data(using: .utf8)!
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase

        let response = try decoder.decode(ExpandResponse.self, from: data)

        XCTAssertNil(response.recipeDraft.category)
        XCTAssertEqual(response.recipeDraft.ingredients.first?.ingredientName, "鸡蛋")
        XCTAssertEqual(response.recipeDraft.steps.first?.stepNumber, 1)
        XCTAssertEqual(response.recipeDraft.warnings, ["请确认内容"])
    }

    func testPydanticValidationErrorBecomesReadableMessage() throws {
        let data = #"{"detail":[{"type":"greater_than","loc":["body","quantity"],"msg":"Input should be greater than 0"}]}"#.data(using: .utf8)!
        let message = APIClient.errorMessage(data, status: 422)
        XCTAssertTrue(message.contains("body.quantity"))
        XCTAssertTrue(message.contains("greater than 0"))
    }

    @MainActor func testConnectionURLAddsAPIRoot() {
        XCTAssertEqual(AppSession.normalizedURL("http://localhost:8000")?.absoluteString, "http://localhost:8000/api")
        XCTAssertNil(AppSession.normalizedURL("localhost:8000"))
        XCTAssertNil(AppSession.normalizedURL("file:///tmp/api"))
    }

    func testHealthIsPublicAndSettingsUsesBearer() async throws {
        URLProtocolStub.handler = { request in
            if request.url?.path == "/api/health" {
                XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
                return (200, #"{"status":"ok","version":"1.0"}"#)
            }
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer secret")
            return (200, #"{"expiration_reminder_days":"2"}"#)
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        let client = APIClient(baseURL: URL(string: "https://example.test/api")!, token: "secret", session: URLSession(configuration: configuration))
        let health = try await client.health()
        let settings = try await client.settings()
        XCTAssertEqual(health.status, "ok")
        XCTAssertEqual(settings.expirationReminderDays, "2")
    }
}

private final class URLProtocolStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, body) = try XCTUnwrap(Self.handler)(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}
