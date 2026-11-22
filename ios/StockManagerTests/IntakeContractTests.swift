import XCTest
@testable import StockManager

final class IntakeContractTests: XCTestCase {
    func testIntakeDecodesDocumentedOperations() throws {
        let response = try decode(IntakeParseResponse.self, Self.operations)
        XCTAssertEqual(response.locale, "en")
        XCTAssertEqual(response.unparsedFragments, ["subtotal"])
        XCTAssertEqual(response.operations.count, 5)
        guard case .add(let milk, nil) = response.operations[0],
              case .update(let id, let changes, let source) = response.operations[1],
              case .delete(let deleted, let reason, nil) = response.operations[2],
              case .clarify(let clarification) = response.operations[3] else {
            return XCTFail("Expected add, update, delete and clarify in wire order")
        }
        XCTAssertEqual(milk.temporaryId, "cand_1a2b3c4d")
        XCTAssertEqual(milk.name, "Milk")
        XCTAssertEqual(milk.quantityValue, 2)
        XCTAssertNil(milk.unopenedExpirationDate)
        XCTAssertEqual(milk.suggestedUnopenedExpirationDate, "2026-11-27")
        XCTAssertEqual(milk.expirationSource, "estimated")
        XCTAssertEqual(milk.source.inputKind, "text")
        XCTAssertEqual(milk.warnings.first?.code, "expiration_date_inferred")
        XCTAssertEqual(id, milk.id)
        XCTAssertEqual(changes["quantity_value"], .integer(3))
        XCTAssertEqual(changes["restock_action"], .null)
        XCTAssertNil(changes["quantity_unit"])
        XCTAssertEqual(source?.imageIndex, 0)
        XCTAssertEqual(deleted, "cand_12345678")
        XCTAssertEqual(reason, "duplicate")
        XCTAssertEqual(clarification.temporaryIds, [milk.id])
        XCTAssertEqual(clarification.questionCode, "ambiguous_date")
        XCTAssertEqual(clarification.question, "When does the milk expire?")
        XCTAssertEqual(response.operations[4], .unknown("future_operation"))
    }

    func testIntakeDraftPreservesUnknownNestedFieldsAndOriginalWireKeys() throws {
        let fixture = Self.milk.replacingOccurrences(
            of: #""source": {"input_kind": "text"}"#,
            with: #""source":{"input_kind":"future_input","future_span":{"offset_start":123}},"future_FLAG":{"futureValues":[true,null,9007199254740993]},"field_confidence":{"quantity_value":0.8}"#
        )
        var candidate = try decode(IntakeCandidate.self, fixture)
        XCTAssertEqual(candidate.source.inputKind, "future_input")
        XCTAssertEqual(candidate.fieldConfidence["quantity_value"], 0.8)
        candidate.name = "Skim milk"
        let request = IntakeParseRequest(input: .init(text: "Correction"), draft: .init(items: [candidate]),
                                         context: .init(locale: "en", timezone: "Asia/Tokyo"))
        let encoded = try encode(request)
        guard case .object(let object) = try decode(JSONValue.self, String(decoding: encoded, as: UTF8.self)),
              case .object(let draft) = object["draft"],
              case .array(let items) = draft["items"],
              case .object(let raw) = items.first else { return XCTFail("Missing draft candidate") }
        XCTAssertEqual(raw["name"], .string("Skim milk"))
        XCTAssertEqual(raw["unopened_expiration_date"], .null)
        XCTAssertEqual(raw["source"], .object(["input_kind": .string("future_input"),
                                               "future_span": .object(["offset_start": .integer(123)])]))
        XCTAssertEqual(raw["future_FLAG"], .object(["futureValues": .array([.bool(true), .null, .integer(9_007_199_254_740_993)])]))
        XCTAssertEqual(raw["field_confidence"], .object(["quantity_value": .number(0.8)]))
    }

    func testIntakeUpdateOnlyMergesPresentFields() throws {
        var item = try decode(IntakeCandidate.self, Self.milk)
        item.owner = "Me"
        item.notes = "Keep in the refrigerator"
        let edits: [String: JSONValue] = ["quantity_value": .number(2.5), "owner": .null,
                                          "restock_action": .string("partial"), "future_status": .string("retained")]
        let updated = try item.applying(edits)
        XCTAssertEqual(updated.id, item.id)
        XCTAssertEqual(updated.quantityValue, 2.5)
        XCTAssertEqual(updated.quantityUnit, "bottles")
        XCTAssertEqual(updated.notes, item.notes)
        XCTAssertNil(updated.owner)
        XCTAssertEqual(updated.restockAction, "partial")
        let json = try JSONSerialization.jsonObject(with: encode(updated)) as? [String: Any]
        XCTAssertTrue(json?["owner"] is NSNull)
        XCTAssertEqual(json?["future_status"] as? String, "retained")
    }

    @MainActor func testIntakeParseSendsCurrentDraftAndAppliesOperationsInOrder() async throws {
        let milk = try decode(IntakeCandidate.self, Self.milk)
        let duplicate = IntakeCandidate.manual(temporaryId: "cand_12345678")
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/intake/parse")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            let json = try Self.body(request)
            XCTAssertEqual(json["input"] as? [String: String], ["type": "text", "text": "Two bottles of milk"])
            XCTAssertEqual(json["context"] as? [String: String],
                           ["locale": "en", "timezone": "Asia/Tokyo", "purchase_date": "2026-11-20"])
            let draft = try XCTUnwrap(json["draft"] as? [String: Any])
            let items = try XCTUnwrap(draft["items"] as? [[String: Any]])
            XCTAssertEqual(items.map { $0["temporary_id"] as? String }, ["cand_12345678"])
            XCTAssertEqual(items.first?["name"] as? String, "Old entry")
            return (200, Self.operations)
        }
        let store = makeStore(client, candidates: [duplicate])
        var edited = duplicate
        edited.name = "Old entry"
        store.replaceCandidate(edited)
        store.purchaseDate = "2026-11-20"

        let succeeded = await store.parse(text: "  Two bottles of milk \n", locale: "en", timezone: "Asia/Tokyo")
        XCTAssertTrue(succeeded)
        XCTAssertEqual(store.action, .succeeded(nil))
        XCTAssertEqual(store.candidates.map(\.id), [milk.id])
        XCTAssertEqual(store.candidates.first?.quantityValue, 3)
        XCTAssertNil(store.candidates.first?.restockAction)
        XCTAssertEqual(store.lastParse?.clarifications.first?.temporaryIds, [milk.id])
        XCTAssertEqual(store.lastParse?.unparsedFragments, ["subtotal"])
        XCTAssertEqual(store.lastParse?.locale, "en")
    }

    @MainActor func testIntakeParseDefaultsToHouseholdLocaleAndTimezone() async throws {
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/intake/parse")
            let body = try Self.body(request)
            let context = try XCTUnwrap(body["context"] as? [String: String])
            let input = try XCTUnwrap(body["input"] as? [String: String])
            XCTAssertEqual(context, input["text"] == "With purchase date" ? ["purchase_date": "2026-11-20"] : [:])
            return (200, #"{"operations":[],"unparsed_fragments":[],"locale":"ja","warnings":[]}"#)
        }
        let store = makeStore(client, candidates: [])
        let withoutDate = await store.parse(text: "Without purchase date")
        XCTAssertTrue(withoutDate)
        store.purchaseDate = "2026-11-20"
        let withDate = await store.parse(text: "With purchase date")
        XCTAssertTrue(withDate)
        XCTAssertEqual(store.lastParse?.locale, "ja")
    }

    @MainActor func testIntakeConfirmEncodesDefaultsOverridesAndRestockLinkThenRefreshes() async throws {
        let inventoryRefresh = expectation(description: "Inventory refreshed after confirmation")
        let restockRefresh = expectation(description: "Restock refreshed after confirmation")
        let milk = try reviewedMilk()
        let receipt = try decode(IntakeCandidate.self, Self.receipt)
        XCTAssertEqual(receipt.rawName, "EGGS 6PK")
        XCTAssertEqual(receipt.source.imageIndex, 1)
        XCTAssertEqual(receipt.specificity, "specific_receipt_label")
        XCTAssertEqual(receipt.aliasMode, "suggest")
        XCTAssertEqual(receipt.suggestions?.first?.confirmedCount, 2)
        XCTAssertEqual(receipt.requiresUserReview, true)
        let client = stubbedClient { request in
            switch (request.httpMethod, request.url?.path) {
            case ("GET", "/api/items"):
                inventoryRefresh.fulfill()
                return (200, "[]")
            case ("GET", "/api/restock"):
                restockRefresh.fulfill()
                return (200, "[]")
            case ("POST", "/api/intake/confirm"):
                XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
                let json = try Self.body(request)
                XCTAssertEqual(json["defaults"] as? [String: String], ["owner": "me", "location": "Fridge"])
                let items = try XCTUnwrap(json["items"] as? [[String: Any]])
                XCTAssertEqual(items.count, 2)
                let first = try XCTUnwrap(items.first)
                XCTAssertEqual(first["unopened_expiration_date"] as? String, "2026-11-27")
                XCTAssertEqual(first["matched_restock_id"] as? Int, 7)
                XCTAssertEqual(first["restock_action"] as? String, "done")
                XCTAssertNil(first["suggested_unopened_expiration_date"])
                XCTAssertNil(first["owner"])
                let override = try XCTUnwrap(items.last)
                XCTAssertEqual(override["owner"] as? String, "Alex")
                XCTAssertEqual(override["location"] as? String, "Pantry")
                XCTAssertEqual(override["raw_name"] as? String, "EGGS 6PK")
                XCTAssertEqual(override["store_name"] as? String, "Market")
                XCTAssertEqual(override["specificity"] as? String, "specific_receipt_label")
                return (201, Self.confirmed)
            default:
                throw URLError(.badURL)
            }
        }
        let store = makeStore(client, candidates: [milk, receipt])
        store.defaults = .init(owner: " me ", location: "Fridge")
        XCTAssertTrue(store.canConfirm)
        let response = await store.confirm()
        await fulfillment(of: [inventoryRefresh, restockRefresh], timeout: 2)
        XCTAssertEqual(response?.created.first?.itemId, 41)
        XCTAssertEqual(response?.restockDone, [7])
        XCTAssertEqual(response?.restockPartial, [])
        XCTAssertTrue(store.candidates.isEmpty)
        XCTAssertEqual(store.action, .succeeded("物品已入库，补货条目之前已完成"))
    }

    @MainActor func testIntakeConfirmationFinishesAfterCallerCancellation() async throws {
        let milk = try reviewedMilk()
        let posted = expectation(description: "Confirmation submitted exactly once")
        posted.assertForOverFulfill = true
        let inventoryRefresh = expectation(description: "Inventory refreshed despite cancellation")
        let restockRefresh = expectation(description: "Restock refreshed despite cancellation")
        let releaseResponse = DispatchSemaphore(value: 0)
        let client = stubbedClient { request in
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/intake/confirm"):
                posted.fulfill()
                guard releaseResponse.wait(timeout: .now() + 5) == .success else { throw URLError(.timedOut) }
                return (201, #"{"created":[{"temporary_id":"cand_1a2b3c4d","item_id":41}],"restock_done":[7],"restock_partial":[],"warnings":[]}"#)
            case ("GET", "/api/items"):
                inventoryRefresh.fulfill()
                return (200, "[]")
            case ("GET", "/api/restock"):
                restockRefresh.fulfill()
                return (200, "[]")
            default:
                throw URLError(.badURL)
            }
        }
        let store = makeStore(client, candidates: [milk])
        store.defaults = .init(owner: "me", location: "Fridge")
        let caller = Task { await store.confirm() }
        await fulfillment(of: [posted], timeout: 2)

        caller.cancel()
        let duplicate = await store.confirm()
        XCTAssertNil(duplicate)
        XCTAssertEqual(store.action, .running)
        releaseResponse.signal()

        let response = await caller.value
        await fulfillment(of: [inventoryRefresh, restockRefresh], timeout: 2)
        XCTAssertEqual(response?.created.map(\.temporaryId), [milk.id])
        XCTAssertTrue(store.candidates.isEmpty)
        XCTAssertEqual(store.action, .succeeded(nil))
    }

    @MainActor func testIntakeRejectedBatchKeepsDraftAndLocatesFieldByIDOrIndex() async throws {
        let milk = try reviewedMilk()
        let receipt = try decode(IntakeCandidate.self, Self.receipt)
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/intake/confirm")
            return (422, #"{"code":"intake_item_invalid","params":{"index":1,"temporary_id":"cand_12345678","field":"quantity_value"},"detail":"Invalid item"}"#)
        }
        let store = makeStore(client, candidates: [milk, receipt])
        store.defaults = .init(owner: "me", location: "Fridge")
        let rejected = await store.confirm()
        XCTAssertNil(rejected)
        XCTAssertEqual(store.candidates, [milk, receipt])
        XCTAssertEqual(store.serverIssue, .init(temporaryId: receipt.id, field: "quantity_value"))

        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/intake/confirm")
            return (422, #"{"code":"intake_item_invalid","params":{"index":0,"field":"category_id"},"detail":"Invalid item"}"#)
        }
        let rejectedByIndex = await store.confirm()
        XCTAssertNil(rejectedByIndex)
        XCTAssertEqual(store.candidates, [milk, receipt])
        XCTAssertEqual(store.serverIssue, .init(temporaryId: milk.id, field: "category_id"))
    }

    @MainActor func testIntakeReplacingCandidateClearsFailureButPreservesUnrelatedFieldIssue() async throws {
        var milk = try reviewedMilk()
        let receipt = try decode(IntakeCandidate.self, Self.receipt)
        let client = stubbedClient { _ in
            (422, #"{"code":"intake_item_invalid","params":{"temporary_id":"cand_12345678","field":"quantity_value"},"detail":"Invalid item"}"#)
        }
        let store = makeStore(client, candidates: [milk, receipt])
        store.defaults = .init(owner: "me", location: "Fridge")

        await store.confirm()
        XCTAssertNotNil(store.action.errorMessage)
        milk.notes = "Reviewed"
        store.replaceCandidate(milk)
        XCTAssertNil(store.action.errorMessage)
        XCTAssertEqual(store.action, .idle)
        XCTAssertEqual(store.serverIssue, .init(temporaryId: receipt.id, field: "quantity_value"))

        await store.confirm()
        XCTAssertNotNil(store.action.errorMessage)
        store.replaceCandidate(receipt)
        XCTAssertEqual(store.action, .idle)
        XCTAssertNil(store.serverIssue)
    }

    @MainActor func testIntakeAddingRemovingAndChangingDefaultsClearFailure() async throws {
        let client = stubbedClient { _ in
            XCTFail("An empty description must be rejected locally")
            return (500, "{}")
        }
        let store = makeStore(client, candidates: [])

        await store.parse(text: "")
        XCTAssertNotNil(store.action.errorMessage)
        let added = try XCTUnwrap(store.addManualCandidate())
        XCTAssertEqual(store.action, .idle)

        await store.parse(text: "")
        XCTAssertNotNil(store.action.errorMessage)
        store.removeCandidate(id: added.id)
        XCTAssertEqual(store.action, .idle)

        await store.parse(text: "")
        XCTAssertNotNil(store.action.errorMessage)
        store.defaults.location = "Fridge"
        XCTAssertEqual(store.action, .idle)
    }

    @MainActor func testIntakeParseFailureDoesNotApplyPartialOperations() async throws {
        let milk = try decode(IntakeCandidate.self, Self.milk)
        let client = stubbedClient { _ in
            (200, #"{"operations":[{"op":"update","temporary_id":"cand_1a2b3c4d","changes":{"name":"Changed"}},{"op":"delete","temporary_id":"cand_00000000","reason_code":"duplicate"}],"unparsed_fragments":[],"locale":"en","warnings":[]}"#)
        }
        let store = makeStore(client, candidates: [milk])
        let succeeded = await store.parse(text: "Correction", locale: "en", timezone: "Asia/Tokyo")
        XCTAssertFalse(succeeded)
        XCTAssertEqual(store.candidates, [milk])
        XCTAssertNil(store.lastParse)
    }

    @MainActor func testIntakeValidatesLimitsAndRequiresActualExpiration() async throws {
        let milk = try decode(IntakeCandidate.self, Self.milk)
        let client = stubbedClient { _ in
            XCTFail("Invalid input must not send a request")
            return (500, "{}")
        }
        let store = makeStore(client, candidates: [milk])
        let empty = await store.parse(text: " \n ")
        let tooLong = await store.parse(text: String(repeating: "乳", count: 4_001))
        XCTAssertFalse(empty)
        XCTAssertFalse(tooLong)
        XCTAssertEqual(store.candidates, [milk])
        store.defaults = .init(owner: "me", location: "Fridge")
        XCTAssertFalse(store.canConfirm)
        XCTAssertEqual(store.confirmationIssues, [.init(temporaryId: milk.id, field: "unopened_expiration_date")])
        var adopted = milk
        adopted.adoptSuggestedExpiration()
        store.replaceCandidate(adopted)
        XCTAssertEqual(adopted.expirationSource, "stated")
        XCTAssertTrue(store.canConfirm)
        let manual = try XCTUnwrap(store.addManualCandidate())
        XCTAssertNotNil(manual.id.range(of: #"^cand_[a-f0-9]{8}$"#, options: .regularExpression))
        XCTAssertNotEqual(manual.id, milk.id)
        XCTAssertEqual(manual.source.inputKind, "text")
        XCTAssertEqual(manual.confidence, 1)

        let overflowing = (0...100).map { IntakeCandidate.manual(temporaryId: String(format: "cand_%08x", $0)) }
        let oversized = makeStore(client, candidates: overflowing)
        let parsed = await oversized.parse(text: "Milk")
        XCTAssertFalse(parsed)
        XCTAssertNil(oversized.addManualCandidate())
        XCTAssertEqual(oversized.candidates.count, 101)
    }

    @MainActor func testIntakeRejectsInvalidDraftFieldsBeforeSendingParse() async throws {
        let milk = try reviewedMilk()
        let client = stubbedClient { _ in
            XCTFail("Invalid draft must not send a request")
            return (500, "{}")
        }
        let valid = IntakeCandidate.manual(temporaryId: "cand_12345678")
        let fields: [(String, JSONValue, String)] = [
            ("quantity_value", .integer(0), "数量"),
            ("category_id", .integer(0), "分类"),
            ("purchase_date", .string("2026-13-40"), "购买日期")
        ]
        for (field, value, label) in fields {
            let invalid = try milk.applying([field: value])
            let store = makeStore(client, candidates: [valid, invalid])
            let expected = IntakeFieldIssue(temporaryId: milk.id, field: field)
            let parsed = await store.parse(text: "Correction")
            XCTAssertFalse(parsed)
            XCTAssertEqual(store.draftIssues, [expected])
            XCTAssertEqual(store.serverIssue, expected)
            XCTAssertEqual(store.action, .failed("草稿中的\(label)无效，请修改后再解析"))
            XCTAssertEqual(store.candidates, [valid, invalid])
            XCTAssertEqual(store.confirmationIssues.filter { $0 == expected }.count, 1)
        }
    }

    func testIntakeDraftChecksOptionalDatesAndTextLimits() throws {
        let candidate = IntakeCandidate.manual(temporaryId: "cand_12345678")
        let valid: [String: JSONValue] = ["quantity_value": .number(1.5), "category_id": .integer(1),
                                          "purchase_date": .string("2028-02-29"), "unopened_expiration_date": .string("infinite"),
                                          "name": .string(String(repeating: "乳", count: 255)), "owner": .null]
        XCTAssertTrue(try candidate.applying(valid).invalidDraftFields.isEmpty)
        let invalid: [String: JSONValue] = [
            "purchase_date": .string("2026-02-29"),
            "suggested_unopened_expiration_date": .string("2026-1-01"),
            "opened_expiration_date": .string("infinite"), "opened_date": .string("2026-01-32"),
            "unopened_expiration_date": .string("2026-01-01T00:00:00Z"),
            "name": .string(String(repeating: "乳", count: 256)), "raw_name": .string(String(repeating: "乳", count: 256)),
            "quantity_unit": .string(String(repeating: "乳", count: 51)), "owner": .string(String(repeating: "乳", count: 101)),
            "location": .string(String(repeating: "乳", count: 101))
        ]
        XCTAssertEqual(try Set(candidate.applying(invalid).invalidDraftFields), Set(invalid.keys))
    }

    func testIntakeWarningsUseKnownTextAndFutureFallback() throws {
        let warning = try decode(AIWarning.self, #"{"code":"op_invalid","params":{"index":"0"}}"#)
        let future = try decode(AIWarning.self, #"{"code":"future_warning","message":"Check this item"}"#)
        let unspecified = try decode(AIWarning.self, #"{"code":"future_warning"}"#)
        XCTAssertEqual(DisplayText.intakeWarning(warning), "第 1 条操作无效，已忽略")
        XCTAssertEqual(DisplayText.intakeWarning(future), "Check this item")
        XCTAssertEqual(DisplayText.intakeWarning(unspecified), "入库结果包含一条提示，请检查内容。")
    }

    @MainActor func testPhotoIntakeBatchesRetryWithoutReapplyingPreviousDraft() async throws {
        let photos = (1...17).map {
            PreparedIntakeImage(jpeg: Data("image-\($0)".utf8), captureDate: "2026-11-20")
        }
        let milk = try decode(IntakeCandidate.self, Self.milk)
        let batches = [Array(1...8), Array(9...16), Array(9...16), [17]]
        var attempts = 0
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/intake/parse")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.timeoutInterval, 120)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            let type = try XCTUnwrap(request.value(forHTTPHeaderField: "Content-Type"))
            XCTAssertTrue(type.hasPrefix("multipart/form-data; boundary="))
            let boundary = String(type.dropFirst("multipart/form-data; boundary=".count))
            let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(APIContractTests.readBody))
            let fields = String(decoding: data, as: UTF8.self).components(separatedBy: "--" + boundary)
            let payloadPart = try XCTUnwrap(fields.first { $0.contains("name=\"payload\"") })
            let json = try XCTUnwrap(payloadPart.components(separatedBy: "\r\n\r\n").last)
            let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
            XCTAssertEqual(Set(payload.keys), ["draft", "context"])
            let draft = try XCTUnwrap(payload["draft"] as? [String: Any])
            let items = try XCTUnwrap(draft["items"] as? [[String: Any]])
            XCTAssertEqual(items.map { $0["temporary_id"] as? String }, attempts == 0 ? [] : [milk.id])
            let context = try XCTUnwrap(payload["context"] as? [String: String])
            XCTAssertEqual(context, ["purchase_date": attempts < 2 ? "2026-11-20" : "2026-11-19"])

            let images = fields.filter { $0.contains("name=\"images\"") }
            let expected = try XCTUnwrap(batches.indices.contains(attempts) ? batches[attempts] : nil)
            XCTAssertEqual(images.count, expected.count)
            for (index, pair) in zip(images, expected).enumerated() {
                XCTAssertTrue(pair.0.contains("filename=\"photo-\(index + 1).jpg\""))
                XCTAssertTrue(pair.0.contains("Content-Type: image/jpeg\r\n\r\nimage-\(pair.1)\r\n"))
            }
            attempts += 1
            if attempts == 1 {
                return (200, """
                {"operations":[{"op":"add","candidate":\(Self.milk)}],"unparsed_fragments":["first"],
                 "locale":"en","warnings":[]}
                """)
            }
            if attempts == 2 {
                return (422, #"{"code":"intake_image_too_large","params":{"index":1},"detail":"Too large"}"#)
            }
            return (200, #"{"operations":[],"unparsed_fragments":["next"],"locale":"en","warnings":[]}"#)
        }
        let store = makeStore(client, candidates: [])
        await store.parse(photos: photos)
        XCTAssertEqual(attempts, 2)
        XCTAssertEqual(store.photoUpload?.batch, 2)
        XCTAssertEqual(store.photoUpload?.totalBatches, 3)
        XCTAssertEqual(store.candidates.map(\.id), [milk.id])
        XCTAssertEqual(store.action.errorMessage, "第 2 张图片超过大小限制")
        store.purchaseDate = "2026-11-19"

        await store.retryPhotoUpload()
        XCTAssertEqual(attempts, 4)
        XCTAssertNil(store.photoUpload)
        XCTAssertEqual(store.action, .succeeded(nil))
        XCTAssertEqual(store.candidates.map(\.id), [milk.id])
        XCTAssertEqual(store.lastParse?.unparsedFragments, ["first", "next", "next"])
    }

    @MainActor func testUnnamedReceiptLinesRequireNamesAndKeepAliasMetadata() throws {
        let nameField = try XCTUnwrap(Self.receipt.range(of: #""name": "Eggs""#))
        let raw = Self.receipt.replacingCharacters(in: nameField, with: #""name": null"#)
        var first = try decode(IntakeCandidate.self, raw)
        var second = try decode(IntakeCandidate.self, raw.replacingOccurrences(of: "cand_12345678", with: "cand_00000002"))
        let client = stubbedClient { _ in (500, "{}") }
        let store = makeStore(client, candidates: [first, second])
        XCTAssertEqual(store.confirmationIssues.map(\.field), ["name", "name"])
        XCTAssertFalse(store.canConfirm)
        first.name = try XCTUnwrap(first.suggestions?.first?.name)
        store.replaceCandidate(first)
        XCTAssertFalse(store.canConfirm)
        second.name = "Eggs"
        store.replaceCandidate(second)
        XCTAssertTrue(store.canConfirm)
        XCTAssertEqual(store.candidates.map(\.id), [first.id, second.id])
        let encoded = try encode(IntakeConfirmItem(candidate: first))
        let item = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        XCTAssertEqual(item["raw_name"] as? String, "EGGS 6PK")
        XCTAssertEqual(item["store_name"] as? String, "Market")
        XCTAssertEqual(item["specificity"] as? String, "specific_receipt_label")
    }

    @MainActor private func makeStore(_ client: APIClient, candidates: [IntakeCandidate]) -> IntakeStore {
        IntakeStore(client: client, inventory: InventoryStore(client: client),
                    restock: RestockStore(client: client), candidates: candidates)
    }

    private func reviewedMilk() throws -> IntakeCandidate {
        let milk = try decode(IntakeCandidate.self, Self.milk)
        return try milk.applying(["unopened_expiration_date": .string("2026-11-27"),
                                  "matched_restock_id": .integer(7), "restock_action": .string("done")])
    }

    private func stubbedClient(_ handler: @escaping (URLRequest) throws -> (Int, String)) -> APIClient {
        URLProtocolStub.handler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return APIClient(baseURL: URL(string: "https://example.test/api")!, token: "test-token",
                         session: URLSession(configuration: configuration))
    }

    private static func body(_ request: URLRequest) throws -> [String: Any] {
        let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(APIContractTests.readBody))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    private func encode(_ value: some Encodable) throws -> Data {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return try encoder.encode(value)
    }

    // Candidate from docs/app/intake.md, Parse text.
    private static let milk = """
    {
      "temporary_id": "cand_1a2b3c4d",
      "name": "Milk",
      "quantity_value": 2,
      "quantity_unit": "bottles",
      "category_id": 12,
      "purchase_date": "2026-11-20",
      "unopened_expiration_date": null,
      "suggested_unopened_expiration_date": "2026-11-27",
      "expiration_source": "estimated",
      "confidence": 0.9,
      "warnings": [{"code": "expiration_date_inferred", "params": {"basis": "category_default"}}],
      "source": {"input_kind": "text"}
    }
    """

    // The other operation shapes follow the documented operation fields table.
    private static let operations = """
    {
      "operations": [
        {"op": "add", "candidate": \(milk)},
        {"op": "update", "temporary_id": "cand_1a2b3c4d",
         "changes": {"quantity_value": 3, "restock_action": null}, "source": {"input_kind": "receipt", "image_index": 0}},
        {"op": "delete", "temporary_id": "cand_12345678", "reason_code": "duplicate"},
        {"op": "clarify", "temporary_ids": ["cand_1a2b3c4d"], "question_code": "ambiguous_date",
         "question": "When does the milk expire?"},
        {"op": "future_operation"}
      ],
      "unparsed_fragments": ["subtotal"], "locale": "en", "warnings": []
    }
    """

    private static let receipt = """
    {
      "temporary_id": "cand_12345678", "name": "Eggs", "category_id": 13,
      "quantity_value": 1, "quantity_unit": "box", "unopened_expiration_date": "infinite",
      "owner": "Alex", "location": "Pantry", "raw_name": "EGGS 6PK", "store_name": "Market",
      "specificity": "specific_receipt_label", "alias_mode": "suggest", "requires_user_review": true,
      "review_reason": "first_seen", "confidence": 0.8, "source": {"input_kind": "receipt", "image_index": 1},
      "suggestions": [{"name": "Eggs", "source": "user_alias_history", "confirmed_count": 2}]
    }
    """

    // Confirm response from docs/app/intake.md with a second reviewed item and a restock warning.
    private static let confirmed = """
    {
      "created": [{"temporary_id": "cand_1a2b3c4d", "item_id": 41}, {"temporary_id": "cand_12345678", "item_id": 42}],
      "restock_done": [7], "restock_partial": [], "warnings": [{"code": "restock_already_done", "params": {"restock_id": "8"}}]
    }
    """
}
