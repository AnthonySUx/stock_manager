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
        let data = Data(#"{"recipe_draft":{"title":"早餐","category":"unknown","ingredients":[{"ingredient_name":"鸡蛋","quantity":"2","unit":"个"}],"steps":[{"instruction":"打散鸡蛋"}],"warnings":{"obsolete":true}},"locale":"zh-CN","warnings":[]}"#.utf8)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase

        let response = try decoder.decode(ExpandResponse.self, from: data)

        XCTAssertNil(response.recipeDraft.category)
        XCTAssertEqual(response.recipeDraft.ingredients.first?.ingredientName, "鸡蛋")
        XCTAssertEqual(response.recipeDraft.steps.first?.stepNumber, 1)
        XCTAssertNil(response.recipeDraft.difficulty)
        XCTAssertNil(response.recipeDraft.servings)
        XCTAssertNil(response.recipeDraft.cookTimeMinutes)
    }

    func testExploreDecodesDocumentedWarningAndLinkedRecipeActions() throws {
        let response = try exploreDecoder.decode(ExploreResponse.self, from: Data(Self.exploreFixture.utf8))
        XCTAssertEqual(response.locale, "zh-CN")
        XCTAssertEqual(response.inputMode, "natural_language")
        XCTAssertEqual(response.warnings.first?.params, ["title": "Tomato soup"])
        XCTAssertEqual(response.warnings.map(DisplayText.aiWarning), ["创意「Tomato soup」的语言不符，已省略"])

        var idea = try XCTUnwrap(response.ideas.first)
        XCTAssertEqual(idea.action, .openRecipe(42))
        idea.canExpandToRecipe = true
        XCTAssertEqual(idea.action, .openRecipe(42))
        idea.sourceType = "ai_idea"
        idea.recipeId = nil
        XCTAssertEqual(idea.action, .expand)
        idea.canExpandToRecipe = false
        XCTAssertEqual(idea.action, .none)
    }

    func testExpandDecodesDocumentedDraftLocaleAndTopLevelWarnings() throws {
        let response = try exploreDecoder.decode(ExpandResponse.self, from: Data(Self.expandFixture.utf8))
        XCTAssertEqual(response.locale, "zh-CN")
        XCTAssertEqual(response.recipeDraft.title, "番茄炒蛋")
        XCTAssertEqual(response.recipeDraft.ingredients.first?.ingredientName, "番茄")
        XCTAssertEqual(response.warnings.map(\.code), ["draft_ai_generated"])
        XCTAssertEqual(response.warnings.map(DisplayText.aiWarning), ["此草稿由 AI 生成，请检查食材、用量和步骤后再保存。"])
    }

    func testUnknownWarningsUseServerTextOrGenericNotice() throws {
        let response = #"{"mode":"ai","input_mode":"natural_language","locale":"zh-CN","ideas":[],"warnings":[{"code":"future","params":{},"message":"A server notice"},{"code":"future","params":{},"detail":"An alternate notice"},{"code":"future","params":{}}]}"#
        let decoded = try exploreDecoder.decode(ExploreResponse.self, from: Data(response.utf8))
        XCTAssertEqual(decoded.warnings.map(DisplayText.aiWarning), [
            "A server notice", "An alternate notice", "AI 结果包含一条提示，请检查内容。"
        ])
    }

    func testExploreDecodesWarningWithNumericParams() throws {
        let fixture = #"{"mode":"ai","input_mode":"natural_language","locale":"zh-CN","ideas":[],"warnings":[{"code":"ingredient_dropped_malformed","params":{"index":2}}]}"#
        let response = try exploreDecoder.decode(ExploreResponse.self, from: Data(fixture.utf8))
        XCTAssertEqual(response.warnings.first?.code, "ingredient_dropped_malformed")
        XCTAssertEqual(response.warnings.first?.params, [:])
    }

    func testDifficultyLabelsKeepLegacyFreeText() {
        XCTAssertEqual(["easy", "medium", "hard", "适合新手"].map(DisplayText.difficulty),
                       ["简单", "中等", "困难", "适合新手"])
    }

    func testExploreAndExpandEncodeRequestsWith120SecondTimeout() async throws {
        let client = stubbedClient { request in
            XCTAssertEqual(request.timeoutInterval, 120)
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(Self.readBody))
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            switch request.url?.path {
            case "/api/recipes/explore":
                XCTAssertEqual(json["mode"] as? String, "natural_language")
                XCTAssertEqual(json["natural_language"] as? String, "想做晚餐")
                XCTAssertNil(json["structured"])
                return (200, Self.exploreFixture)
            case "/api/recipes/explore/expand":
                let idea = try XCTUnwrap(json["idea"] as? [String: Any])
                XCTAssertEqual(idea["source_type"] as? String, "ai_idea")
                XCTAssertEqual(idea["idea_id"] as? String, "3f2a9c1b")
                XCTAssertNil(json["locale"])
                return (200, Self.expandFixture)
            default:
                throw URLError(.badURL)
            }
        }
        let explore = try await client.explore(.init(mode: "natural_language", structured: nil, naturalLanguage: "想做晚餐"))
        var idea = try XCTUnwrap(explore.ideas.first)
        idea.sourceType = "ai_idea"
        idea.recipeId = nil
        idea.canExpandToRecipe = true
        let expand = try await client.expand(idea)
        XCTAssertEqual(expand.locale, "zh-CN")
    }

    @MainActor func testExploreRetainsResultsAndRetriesAfter502() async throws {
        let request = ExploreRequest(mode: "natural_language", structured: nil, naturalLanguage: "Dinner")
        let client = stubbedClient { req in
            req.url?.path == "/api/capabilities"
                ? (200, #"{"ai":{"text":true,"vision":false,"asr":false}}"#)
                : (200, try Self.streamFixture())
        }
        let capabilities = CapabilitiesStore()
        let store = ExploreStore(client: client, capabilities: capabilities)
        await capabilities.refresh(using: client)
        _ = await store.perform(.generate(request))
        let previous = try XCTUnwrap(store.state.results)

        URLProtocolStub.handler = { _ in (502, #"{"code":"ai_upstream_error"}"#) }
        _ = await store.perform(.generate(request))
        guard case .failed(let retained, let message, .generate(let retry)?) = store.state else {
            return XCTFail("Expected a failed generation with a retry")
        }
        XCTAssertEqual(retained, previous)
        XCTAssertEqual(message, "AI 服务暂时不可用，请重试")
        XCTAssertEqual(retry.naturalLanguage, request.naturalLanguage)

        URLProtocolStub.handler = { _ in (200, try Self.streamFixture()) }
        _ = await store.perform(.generate(retry))
        guard case .loaded = store.state else { return XCTFail("Retry should restore a loaded response") }
    }

    @MainActor func testExplore503RefreshesCapabilitiesAndDisablesNewRequests() async throws {
        let request = ExploreRequest(mode: "natural_language", structured: nil, naturalLanguage: "Dinner")
        let client = stubbedClient { _ in (200, #"{"ai":{"text":true,"vision":true,"asr":false}}"#) }
        let capabilities = CapabilitiesStore()
        let store = ExploreStore(client: client, capabilities: capabilities)
        await capabilities.refresh(using: client)

        URLProtocolStub.handler = { req in
            XCTAssertEqual(req.url?.path, "/api/recipes/explore/stream")
            return (200, try Self.streamFixture())
        }
        _ = await store.perform(.generate(request))
        let previous = try XCTUnwrap(store.state.results)
        let refreshed = expectation(description: "Capabilities refreshed after 503")
        URLProtocolStub.handler = { req in
            if req.url?.path == "/api/capabilities" {
                refreshed.fulfill()
                return (200, #"{"ai":{"text":false,"vision":true,"asr":false}}"#)
            }
            return (503, #"{"code":"ai_unavailable"}"#)
        }
        _ = await store.perform(.generate(request))
        await fulfillment(of: [refreshed], timeout: 1)
        XCTAssertFalse(store.isAvailable)
        XCTAssertTrue(capabilities.value.ai.vision)
        XCTAssertEqual(store.state.results, previous)

        URLProtocolStub.handler = { _ in
            XCTFail("A disabled Explore operation must not call the API")
            return (500, "{}")
        }
        _ = await store.perform(.generate(request))
    }

    func testExploreStreamParserPreservesBoundariesAndFlushesFinalEvent() throws {
        let wire = try Self.ideaEvent() + ": ping\r\n\r\n"
            + "event: error\r\ndata: {\r\ndata:\"code\":\"internal_error\"}"
        var parser = ExploreStreamParser()
        var events: [ExploreStreamEvent] = []
        for byte in wire.utf8 {
            if let event = try parser.receive(byte) { events.append(event) }
        }
        XCTAssertEqual(events.count, 1)
        guard case .idea(let idea) = try XCTUnwrap(events.first) else { return XCTFail("Expected an idea") }
        XCTAssertEqual(idea.title, "番茄炒蛋")
        XCTAssertEqual(try parser.finish(), .error(code: "internal_error"))
    }

    func testExploreStreamEncodesPostAndDecodesFinalWarnings() async throws {
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/recipes/explore/stream")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "text/event-stream")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(Self.readBody))
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(json["mode"] as? String, "structured")
            let preferences = try XCTUnwrap(json["structured"] as? [String: Any])
            XCTAssertEqual(preferences["inventory_item_ids"] as? [Int], [12, 15])
            XCTAssertEqual(preferences["flavors"] as? [String], ["spicy"])
            XCTAssertNil(json["natural_language"])
            return (200, try Self.streamFixture())
        }
        let request = ExploreRequest(mode: "structured", structured: .init(inventoryItemIds: [12, 15], flavors: ["spicy"]),
                                     naturalLanguage: nil)
        var events: [ExploreStreamEvent] = []
        for try await event in client.exploreStream(request) { events.append(event) }

        XCTAssertEqual(events.count, 2)
        guard case .idea(let idea) = events.first, case .done(let completion) = events.last else {
            return XCTFail("Expected an idea followed by done")
        }
        XCTAssertEqual(idea.recipeId, 42)
        XCTAssertEqual(completion.mode, "ai")
        XCTAssertEqual(completion.inputMode, "natural_language")
        XCTAssertEqual(completion.locale, "zh-CN")
        XCTAssertEqual(completion.count, 1)
        XCTAssertEqual(completion.warnings.first?.params["title"], "Tomato soup")
    }

    func testExploreStreamDecodesHTTPValidationError() async throws {
        let client = stubbedClient { _ in
            (422, #"{"detail":[{"loc":["body","natural_language"],"msg":"Field required"}]}"#)
        }
        let request = ExploreRequest(mode: "natural_language", structured: nil, naturalLanguage: nil)
        do {
            for try await _ in client.exploreStream(request) { XCTFail("Unexpected event") }
            XCTFail("Expected an HTTP error")
        } catch let error as APIClientError {
            XCTAssertEqual(error, .server(status: 422, code: nil, params: [:], fallback: "body.natural_language：Field required"))
        }
    }

    @MainActor func testExploreStreamErrorKeepsPartialIdeasAndOffersRetry() async throws {
        let client = stubbedClient { request in
            if request.url?.path == "/api/capabilities" {
                return (200, #"{"ai":{"text":true,"vision":false,"asr":false}}"#)
            }
            return (200, try Self.ideaEvent() + "event: error\ndata: {\"code\":\"internal_error\"}\n\n")
        }
        let capabilities = CapabilitiesStore()
        let store = ExploreStore(client: client, capabilities: capabilities)
        await capabilities.refresh(using: client)
        let request = ExploreRequest(mode: "natural_language", structured: nil, naturalLanguage: "Dinner")
        _ = await store.perform(.generate(request))

        guard case .failed(let partial, let message, .generate(let retry)?) = store.state else {
            return XCTFail("Expected a retryable stream error")
        }
        XCTAssertEqual(partial?.ideas.map(\.title), ["番茄炒蛋"])
        XCTAssertNil(partial?.completion)
        XCTAssertEqual(message, "服务器内部错误，请重试")
        XCTAssertEqual(retry.naturalLanguage, "Dinner")
    }

    @MainActor func testCancellingExploreStreamStopsNetworkAndKeepsOnlyReceivedIdeas() async throws {
        let stopped = expectation(description: "URLProtocol stream was stopped")
        let ideaEvent = try Self.ideaEvent()
        URLProtocolStub.holdOpen = true
        URLProtocolStub.onStop = { stopped.fulfill() }
        defer {
            URLProtocolStub.holdOpen = false
            URLProtocolStub.onStop = nil
        }
        let client = stubbedClient { request in
            request.url?.path == "/api/capabilities"
                ? (200, #"{"ai":{"text":true,"vision":false,"asr":false}}"#) : (200, ideaEvent)
        }
        let capabilities = CapabilitiesStore()
        let store = ExploreStore(client: client, capabilities: capabilities)
        await capabilities.refresh(using: client)
        let request = ExploreRequest(mode: "natural_language", structured: nil, naturalLanguage: "Dinner")
        let task = Task { await store.perform(.generate(request)) }
        defer { task.cancel() }

        for _ in 0..<100 where store.state.results?.ideas.isEmpty != false {
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertTrue(store.state.isGenerating)
        XCTAssertEqual(store.state.results?.ideas.map(\.title), ["番茄炒蛋"])
        task.cancel()
        _ = await task.value
        await fulfillment(of: [stopped], timeout: 10)
        XCTAssertFalse(store.state.isLoading)
        XCTAssertEqual(store.state.results?.ideas.map(\.title), ["番茄炒蛋"])
        XCTAssertNil(store.state.results?.completion)
    }

    private static func ideaEvent() throws -> String {
        let response = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(exploreFixture.utf8)) as? [String: Any])
        let idea = try XCTUnwrap((response["ideas"] as? [[String: Any]])?.first)
        let json = try JSONSerialization.data(withJSONObject: idea)
        return "event: idea\ndata: \(String(decoding: json, as: UTF8.self))\n\n"
    }

    private static func streamFixture() throws -> String {
        try ideaEvent() + """
        : ping

        event: done
        data: {"mode":"ai","input_mode":"natural_language","locale":"zh-CN",
        data: "warnings":[{"code":"idea_dropped_wrong_language","params":{"title":"Tomato soup"}}],"count":1}


        """
    }

    func testCookConsumptionUsesLocalizedAmountsForValidationAndEncoding() throws {
        let item = ConsumePreviewItem(ingredientName: "豆腐", itemId: 7, itemName: "豆腐",
                                      availableQuantity: 2, availableUnit: "盒", recipeQuantity: nil,
                                      suggestedQuantity: nil, unit: "盒", needsUserInput: true,
                                      status: "active", currentExpirationDate: nil, confidence: "high")
        let preview = ConsumePreview(recipeId: 42, title: "红烧豆腐", suggestions: [item], unmatchedIngredients: [])
        for input in ["１．５", "1,5"] {
            let items = try XCTUnwrap(preview.consumption(selected: [7], amounts: [7: input]))
            let body = try encodedObject(CookRequest(consumeItems: items, notes: nil))
            let values = try XCTUnwrap(body["consume_items"] as? [[String: Any]])
            XCTAssertEqual(values.first?["quantity"] as? Double, 1.5)
        }
        XCTAssertNil(preview.consumption(selected: [7], amounts: [7: "2,5"]))
        XCTAssertNil(preview.consumption(selected: [7], amounts: [7: "0"]))
        XCTAssertNil(preview.consumption(selected: [7, 8], amounts: [7: "1"]))
    }

    private var exploreDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    // recipes.md's Explore idea / done examples and warning parameter table.
    private static let exploreFixture = """
    {
      "mode": "ai", "input_mode": "natural_language", "locale": "zh-CN",
      "ideas": [{"idea_id": "3f2a9c1b", "title": "番茄炒蛋", "source_type": "existing_recipe", "recipe_id": 42,
                 "matched_ingredients": [], "expiring_ingredients": [], "missing_ingredients": [],
                 "flavors": [], "textures": [], "can_expand_to_recipe": false}],
      "warnings": [{"code": "idea_dropped_wrong_language", "params": {"title": "Tomato soup"}}]
    }
    """

    // recipes.md's Expand Idea to Draft example.
    private static let expandFixture = """
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

    func testPydanticValidationErrorBecomesReadableMessage() throws {
        let data = Data(#"{"detail":[{"loc":["body","items",0,"quantity"],"msg":"Input should be greater than 0"},{"loc":["body","owner"],"msg":"Field required"}]}"#.utf8)
        let error = APIClient.serverError(data, status: 422, method: "POST", path: "intake/confirm")
        XCTAssertEqual(error.localizedDescription, "body.items.0.quantity：Input should be greater than 0\nbody.owner：Field required")
    }

    func testCodeOnlyAIErrorUsesChineseMessage() async throws {
        let error = try await stubbedServerError(status: 502, body: #"{"code":"ai_upstream_error"}"#)
        XCTAssertEqual(error, .server(status: 502, code: "ai_upstream_error", params: [:], fallback: "请求失败（502）"))
        XCTAssertEqual(error.localizedDescription, "AI 服务暂时不可用，请重试")
    }

    func testIntakeErrorPreservesParamsAndPrefersCode() async throws {
        let error = try await stubbedServerError(status: 422, body: #"{"code":"intake_item_invalid","params":{"index":1,"temporary_id":"cand_abcd1234","field":"quantity_value"},"detail":"Invalid intake item"}"#)
        XCTAssertEqual(error, .server(status: 422, code: "intake_item_invalid", params: [
            "index": .integer(1), "temporary_id": .string("cand_abcd1234"), "field": .string("quantity_value")
        ], fallback: "Invalid intake item"))
        XCTAssertEqual(error.localizedDescription, "第 2 个条目的入库信息无效，请检查后重试")
    }

    func testLegacyErrorFallbacksKeepDetailAndOnlySpecialCaseRestockCompletion() {
        let data = Data(#"{"detail":"Recipe not found"}"#.utf8)
        XCTAssertEqual(APIClient.serverError(data, status: 404, method: "GET", path: "recipes/1").localizedDescription, "Recipe not found")

        let conflict = Data(#"{"detail":"Already done"}"#.utf8)
        XCTAssertEqual(APIClient.serverError(conflict, status: 409, method: "POST", path: "restock/1/done").localizedDescription, "这条补货之前已经入库，无需重复操作")
        XCTAssertEqual(APIClient.serverError(conflict, status: 409, method: "PATCH", path: "restock/1").localizedDescription, "Already done")
        XCTAssertEqual(APIClient.serverError(Data(), status: 500, method: "GET", path: "settings").localizedDescription, "请求失败（500）")

        let future = Data(#"{"code":"future_error","detail":"Unrecognized error"}"#.utf8)
        XCTAssertEqual(APIClient.serverError(future, status: 400, method: "GET", path: "settings").localizedDescription, "Unrecognized error")

        let futureWithoutDetail = Data(#"{"code":"future_error"}"#.utf8)
        XCTAssertEqual(APIClient.serverError(futureWithoutDetail, status: 400, method: "GET", path: "settings").localizedDescription, "请求失败（400）")
    }

    @MainActor func testCapabilitiesUsesBearerAndFallsBackAfterFailedRefresh() async {
        let store = CapabilitiesStore()
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/capabilities")
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            return (200, #"{"ai":{"text":true,"vision":false,"asr":false}}"#)
        }
        XCTAssertEqual(store.phase, .idle)
        XCTAssertEqual(store.value, .unavailable)

        await store.refresh(using: client)

        XCTAssertEqual(store.phase, .loaded)
        XCTAssertEqual(store.value.ai, .init(text: true, vision: false, asr: false))
        let failing = stubbedClient { _ in (503, #"{"code":"ai_unavailable"}"#) }
        await store.refresh(using: failing)

        XCTAssertEqual(store.phase, .failed("AI 功能未开启"))
        XCTAssertEqual(store.value, .unavailable)

        let recovered = stubbedClient { _ in (200, #"{"ai":{"text":false,"vision":true,"asr":true}}"#) }
        await store.refresh(using: recovered)
        XCTAssertEqual(store.phase, .loaded)
        XCTAssertEqual(store.value.ai, .init(text: false, vision: true, asr: true))

        store.reset()
        XCTAssertEqual(store.phase, .idle)
        XCTAssertEqual(store.value, .unavailable)
    }

    func testSettingsPatchOnlyEncodesChangesAndClearsWithEmptyStrings() async throws {
        let saved = AppSettings(expirationReminderDays: "3", defaultLocale: "en", defaultTimezone: "Asia/Tokyo")
        var draft = HouseholdSettingsDraft(settings: saved)
        XCTAssertNil(draft.changes(from: saved))

        draft.reminderDays = 4
        XCTAssertEqual(try encodedObject(XCTUnwrap(draft.changes(from: saved))) as? [String: String],
                       ["expiration_reminder_days": "4"])

        draft = .init(settings: saved)
        draft.timezone = nil
        draft.locale = nil
        let changes = try XCTUnwrap(draft.changes(from: saved))
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/settings")
            XCTAssertEqual(request.httpMethod, "PATCH")
            let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(Self.readBody))
            let json = try JSONSerialization.jsonObject(with: data) as? [String: String]
            XCTAssertEqual(json, ["default_locale": "", "default_timezone": ""])
            return (200, #"{"expiration_reminder_days":"3","default_locale":null,"default_timezone":null}"#)
        }
        let result = try await client.updateSettings(changes)
        XCTAssertNil(result.defaultLocale)
        XCTAssertNil(result.defaultTimezone)
    }

    func testInventoryShelfLifeRecalculatesUntilExpirationIsEdited() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(secondsFromGMT: 0))
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-21T18:00:00Z"))
        let tokyo = try XCTUnwrap(TimeZone(identifier: "Asia/Tokyo"))
        let purchase = try XCTUnwrap(calendar.date(from: DateComponents(year: 2026, month: 11, day: 22)))
        var draft = ItemDraft()
        draft.useHouseholdToday(now, in: tokyo, calendar: calendar)
        XCTAssertEqual(draft.purchaseDate, purchase)
        XCTAssertNil(draft.explicitPurchaseDate)
        draft.applyShelfLife(7, calendar: calendar)
        XCTAssertEqual(draft.unopenedExpiration, .dated(try XCTUnwrap(calendar.date(byAdding: .day, value: 7, to: purchase))))
        XCTAssertEqual(draft.unopenedExpirationSource, .categoryDefault)
        draft.applyShelfLife(nil, calendar: calendar)
        XCTAssertEqual(draft.unopenedExpiration, .dated(purchase))
        XCTAssertEqual(draft.unopenedExpirationSource, .initial)

        let manualPurchase = try XCTUnwrap(calendar.date(byAdding: .day, value: 2, to: purchase))
        draft.setPurchaseDate(manualPurchase)
        draft.useHouseholdToday(now, in: tokyo, calendar: calendar)
        XCTAssertEqual(draft.purchaseDate, manualPurchase)
        draft.applyShelfLife(1, calendar: calendar)
        XCTAssertEqual(draft.unopenedExpiration, .dated(try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: manualPurchase))))

        let manualExpiration = ExpirationChoice.dated(try XCTUnwrap(calendar.date(byAdding: .day, value: 15, to: purchase)))
        draft.setUnopenedExpiration(manualExpiration)
        draft.applyShelfLife(30, calendar: calendar)
        XCTAssertEqual(draft.unopenedExpiration, manualExpiration)
        XCTAssertEqual(draft.unopenedExpirationSource, .manual)
        draft.setUnopenedExpiration(.infinite)
        draft.applyShelfLife(3, calendar: calendar)
        XCTAssertEqual(draft.unopenedExpiration, .infinite)
    }

    @MainActor func testInventoryOnlySendsPurchaseDateOnCreateWhenEdited() async throws {
        let item = #"{"id":1,"name":"牛奶","category_id":7,"category":{"id":7,"name":"饮品","slug":"drink","recipe_usage":"conditional","is_system":true,"sort_order":2},"owner":"全家","purchase_date":"2026-11-16","quantity_value":2,"quantity_unit":"盒","location":"冰箱","unopened_expiration_date":"infinite","current_expiration_date":"infinite","status":"active"}"#
        func makeClient(expectedPurchaseDate: String?, editing: Bool) -> APIClient {
            stubbedClient { request in
                if request.httpMethod == "GET" { return (200, "[]") }
                XCTAssertEqual(request.url?.path, editing ? "/api/items/1" : "/api/items")
                XCTAssertEqual(request.httpMethod, editing ? "PATCH" : "POST")
                let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(Self.readBody))
                let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
                if let expectedPurchaseDate { XCTAssertEqual(json["purchase_date"] as? String, expectedPurchaseDate) }
                else { XCTAssertNil(json["purchase_date"]) }
                return (200, item)
            }
        }
        let existing = try exploreDecoder.decode(StockItem.self, from: Data(item.utf8))
        var draft = ItemDraft(item: existing)
        try await InventoryStore(client: makeClient(expectedPurchaseDate: nil, editing: false)).save(draft, editing: nil)
        try await InventoryStore(client: makeClient(expectedPurchaseDate: "2026-11-16", editing: true)).save(draft, editing: 1)
        draft.setPurchaseDate(try XCTUnwrap(API.date("2026-11-17")))
        try await InventoryStore(client: makeClient(expectedPurchaseDate: "2026-11-17", editing: false)).save(draft, editing: nil)
    }

    @MainActor func testSystemCategoryCanClearShelfLifeWithoutSendingProtectedFields() async throws {
        let original = #"{"id":7,"name":"蔬菜","slug":"vegetables","recipe_usage":"always","is_system":true,"sort_order":0,"default_shelf_life_days":7}"#
        let category = try exploreDecoder.decode(Category.self, from: Data(original.utf8))
        let client = stubbedClient { request in
            if request.httpMethod == "GET" { return (200, "[]") }
            XCTAssertEqual(request.url?.path, "/api/categories/7")
            XCTAssertEqual(request.httpMethod, "PATCH")
            let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(Self.readBody))
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertNil(json["name"])
            XCTAssertNil(json["parent_id"])
            XCTAssertTrue(json["default_shelf_life_days"] is NSNull)
            return (200, original)
        }
        try await CategoryStore(client: client).update(category, name: category.name, parent: nil,
                                                       usage: .always, order: 0, shelfLife: nil)
    }

    @MainActor func testFullWidthShelfLifeInputSavesIntegerDays() async throws {
        let category = Category(id: 7, name: "蔬菜", slug: "vegetables", recipeUsage: .always,
                                isSystem: true, sortOrder: 0, defaultShelfLifeDays: 7)
        let client = stubbedClient { request in
            if request.httpMethod == "GET" { return (200, "[]") }
            XCTAssertEqual(request.url?.path, "/api/categories/7")
            XCTAssertEqual(request.httpMethod, "PATCH")
            let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(Self.readBody))
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(json["default_shelf_life_days"] as? Int, 30)
            return (200, #"{"id":7,"name":"蔬菜","slug":"vegetables","recipe_usage":"always","is_system":true,"sort_order":0,"default_shelf_life_days":30}"#)
        }
        let days = try XCTUnwrap("３０".shelfLifeDays)
        try await CategoryStore(client: client).update(category, name: category.name, parent: nil,
                                                       usage: .always, order: 0, shelfLife: days)
    }

    func testSettingsDecodesHouseholdLocaleAndTimezoneWhenPresent() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let current = Data(#"{"expiration_reminder_days":"3","default_locale":"zh-CN","default_timezone":"Asia/Tokyo"}"#.utf8)
        let settings = try decoder.decode(AppSettings.self, from: current)
        XCTAssertEqual(settings.defaultLocale, "zh-CN")
        XCTAssertEqual(settings.defaultTimezone, "Asia/Tokyo")

        let legacy = Data(#"{"expiration_reminder_days":"3"}"#.utf8)
        let legacySettings = try decoder.decode(AppSettings.self, from: legacy)
        XCTAssertNil(legacySettings.defaultLocale)
        XCTAssertNil(legacySettings.defaultTimezone)
    }

    func testCategoryDecodesShelfLifeAndToleratesUnknownRecipeUsage() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let current = Data(#"{"id":1,"name":"鸡蛋","slug":"eggs","recipe_usage":"future_usage","is_system":true,"sort_order":0,"default_shelf_life_days":30}"#.utf8)
        let category = try decoder.decode(Category.self, from: current)
        XCTAssertEqual(category.defaultShelfLifeDays, 30)
        XCTAssertEqual(category.recipeUsage.title, "future_usage")

        let legacy = Data(#"{"id":1,"name":"鸡蛋","slug":"eggs","recipe_usage":"always","is_system":true,"sort_order":0}"#.utf8)
        XCTAssertNil(try decoder.decode(Category.self, from: legacy).defaultShelfLifeDays)
    }

    func testCategoryWritesEncodeShelfLifeAndPreservePatchTriState() throws {
        let create = CategoryCreate(name: "鸡蛋", parentId: nil, recipeUsage: nil, sortOrder: 0, defaultShelfLifeDays: 30)
        let omitted = CategoryUpdate(name: nil, parentId: nil, includeParentId: false, recipeUsage: nil, sortOrder: nil)
        var clear = omitted
        clear.includeDefaultShelfLifeDays = true
        var set = clear
        set.defaultShelfLifeDays = 7

        let key = "default_shelf_life_days"
        XCTAssertEqual(try encodedObject(create)[key] as? Int, 30)
        XCTAssertNil(try encodedObject(omitted)[key])
        XCTAssertTrue(try encodedObject(clear)[key] is NSNull)
        XCTAssertEqual(try encodedObject(set)[key] as? Int, 7)
    }

    func testMultipartRequestEncodesOrderedFilesAndTextField() async throws {
        let payload = #"{"draft":{"items":[]},"context":{"locale":"en"}}"#
        let first = Data([0xff, 0xd8, 0x00])
        let second = Data([0xff, 0xd8, 0x01])
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/intake/parse")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.timeoutInterval, 120)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            let contentType = try XCTUnwrap(request.value(forHTTPHeaderField: "Content-Type"))
            let prefix = "multipart/form-data; boundary="
            XCTAssertTrue(contentType.hasPrefix(prefix))
            let boundary = String(contentType.dropFirst(prefix.count))
            XCTAssertNotNil(UUID(uuidString: boundary))

            var expected = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"payload\"\r\n\r\n\(payload)\r\n".utf8)
            for (name, bytes) in [("receipt-a.jpg", first), ("receipt-b.jpg", second)] {
                expected.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"images\"; filename=\"\(name)\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
                expected.append(bytes)
                expected.append(contentsOf: "\r\n".utf8)
            }
            expected.append(contentsOf: "--\(boundary)--\r\n".utf8)
            XCTAssertEqual(try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(Self.readBody)), expected)
            return (200, #"{"message":"ok"}"#)
        }
        let response: MessageResponse = try await client.sendMultipart(path: "intake/parse", fields: ["payload": payload], files: [
            .init(field: "images", filename: "receipt-a.jpg", contentType: "image/jpeg", data: first),
            .init(field: "images", filename: "receipt-b.jpg", contentType: "image/jpeg", data: second)
        ], timeout: 120)
        XCTAssertEqual(response.message, "ok")
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

    private func stubbedServerError(status: Int, body: String) async throws -> APIClientError {
        let client = stubbedClient { _ in (status, body) }
        do {
            _ = try await client.settings()
        } catch let error as APIClientError {
            return error
        }
        throw URLError(.badServerResponse)
    }

    private func stubbedClient(_ handler: @escaping (URLRequest) throws -> (Int, String)) -> APIClient {
        URLProtocolStub.handler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return APIClient(baseURL: URL(string: "https://example.test/api")!, token: "test-token", session: URLSession(configuration: configuration))
    }

    private func encodedObject(_ value: some Encodable) throws -> [String: Any] {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(value)) as? [String: Any])
    }

    static func readBody(_ stream: InputStream) throws -> Data {
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 1024)
        while true {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count == 0 { return data }
            if count < 0 { throw stream.streamError ?? URLError(.cannotDecodeRawData) }
            data.append(contentsOf: buffer.prefix(count))
        }
    }
}

final class URLProtocolStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    static var holdOpen = false
    static var onStop: (() -> Void)?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, body) = try XCTUnwrap(Self.handler)(request)
            let isStream = request.url?.path == "/api/recipes/explore/stream" && status == 200
            let mimeType = isStream ? "text/event-stream" : "application/json"
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": mimeType])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            if !isStream || !Self.holdOpen { client?.urlProtocolDidFinishLoading(self) }
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {
        if request.url?.path == "/api/recipes/explore/stream" { Self.onStop?() }
    }
}
