import XCTest

final class StockManagerUITests: XCTestCase {
    func testConsumeQuantityAcceptsDecimalInput() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-consume"]
        app.launch()
        let field = app.textFields["inventory.consume.quantity"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("1.5")
        XCTAssertEqual(field.value as? String, "1.5")
        XCTAssertTrue(app.buttons["确认"].isEnabled)
    }

    func testFirstLaunchShowsSecureConnectionForm() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-reset"]
        app.launch()
        XCTAssertTrue(app.textFields["connection.url"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.secureTextFields["connection.token"].exists)
        XCTAssertFalse(app.buttons["connection.submit"].isEnabled)
    }

    func testExploreOpensLinkedRecipeAndSavesExpandedDraft() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-reset", "-ui-testing-explore"]
        app.launch()
        openExplore(in: app)

        let prompt = app.descendants(matching: .any)["explore.prompt"].firstMatch
        XCTAssertTrue(prompt.waitForExistence(timeout: 5))
        prompt.tap()
        prompt.typeText("Dinner with eggs or tofu")
        let generate = app.buttons["explore.generate"]
        XCTAssertTrue(generate.isEnabled)
        generate.tap()

        let linked = app.staticTexts["菜谱库已有"]
        XCTAssertTrue(linked.waitForExistence(timeout: 5))
        let expand = app.buttons["展开为菜谱草稿"]
        XCTAssertEqual(app.buttons.matching(identifier: "展开为菜谱草稿").count, 1)
        capture("F2 Explore results")

        linked.tap()
        let details = app.navigationBars["菜谱详情"]
        XCTAssertTrue(details.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["简单"].waitForExistence(timeout: 5))
        details.buttons.firstMatch.tap()

        XCTAssertTrue(expand.waitForExistence(timeout: 5))
        if !expand.isHittable { app.swipeUp() }
        expand.tap()
        let editor = app.navigationBars["新建菜谱"]
        XCTAssertTrue(editor.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["AI 草稿提示"].exists)
        XCTAssertTrue(app.staticTexts["此草稿由 AI 生成，请检查食材、用量和步骤后再保存。"].exists)
        capture("F2 AI draft editor")

        editor.buttons["保存"].tap()
        XCTAssertTrue(linked.waitForExistence(timeout: 5))
        XCTAssertFalse(editor.exists)
    }

    func testExploreDisablesGenerationWhenTextAIIsUnavailable() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-reset", "-ui-testing-explore", "-ui-testing-explore-unavailable"]
        app.launch()
        openExplore(in: app)
        let prompt = app.descendants(matching: .any)["explore.prompt"].firstMatch
        XCTAssertTrue(prompt.waitForExistence(timeout: 5))
        prompt.tap()
        prompt.typeText("Dinner")
        XCTAssertTrue(app.staticTexts["AI 功能未开启"].exists)
        XCTAssertFalse(app.buttons["explore.generate"].isEnabled)
    }

    func testExploreShowsFirstIdeaBeforeCompletionAndCanStop() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-reset", "-ui-testing-explore", "-ui-testing-explore-stream-progress"]
        app.launch()
        openExplore(in: app)
        let prompt = app.descendants(matching: .any)["explore.prompt"].firstMatch
        XCTAssertTrue(prompt.waitForExistence(timeout: 5))
        prompt.tap()
        prompt.typeText("Dinner")
        app.buttons["explore.generate"].tap()

        let idea = app.staticTexts["菜谱库已有"]
        let stop = app.buttons["explore.stop"]
        XCTAssertTrue(idea.waitForExistence(timeout: 5))
        XCTAssertTrue(stop.exists)
        XCTAssertFalse(app.staticTexts["红烧豆腐"].exists)
        capture("F3 first idea while stream is open")

        stop.tap()
        XCTAssertTrue(app.buttons["explore.generate"].waitForExistence(timeout: 5))
        XCTAssertTrue(idea.exists)
        XCTAssertFalse(stop.exists)
    }

    func testHouseholdSettingsSearchesTimezonesAndRollsBackValidationFailure() {
        let app = launchHouseholdSettings()
        let timezone = app.descendants(matching: .any)["settings.householdTimezone"].firstMatch
        XCTAssertTrue(timezone.waitForExistence(timeout: 5))
        if !timezone.isHittable { app.swipeUp() }
        XCTAssertEqual(timezone.value as? String, "Asia/Tokyo")
        capture("F4 household settings")

        timezone.tap()
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["settings.timezone.device"].exists)
        search.tap()
        search.typeText("Paris")
        let paris = app.buttons["settings.timezone.Europe/Paris"]
        XCTAssertTrue(paris.waitForExistence(timeout: 5))
        paris.tap()
        XCTAssertTrue(timezone.waitForExistence(timeout: 5))
        XCTAssertEqual(timezone.value as? String, "Europe/Paris")

        let save = app.buttons["settings.saveHousehold"]
        if !save.isHittable { app.swipeUp() }
        XCTAssertTrue(save.isEnabled)
        save.tap()
        let alert = app.alerts.firstMatch
        XCTAssertTrue(alert.waitForExistence(timeout: 5))
        XCTAssertTrue(alert.staticTexts["时区设置未通过验证"].exists)
        alert.buttons.firstMatch.tap()
        XCTAssertEqual(timezone.value as? String, "Asia/Tokyo")
        XCTAssertFalse(save.isEnabled)
    }

    func testSystemCategoryShelfLifeIsEditableAndValidated() {
        let app = launchHouseholdSettings()
        let manage = app.buttons["分类管理"]
        if !manage.isHittable { app.swipeUp() }
        XCTAssertTrue(manage.waitForExistence(timeout: 5))
        manage.tap()
        let category = app.buttons["categories.row.7"]
        XCTAssertTrue(category.waitForExistence(timeout: 5))
        category.tap()
        let field = app.textFields["category.defaultShelfLife"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        XCTAssertEqual(field.value as? String, "7")
        capture("F4 system category shelf life")

        field.tap()
        field.typeText("9999")
        XCTAssertTrue(app.staticTexts["请输入 1 到 3650 的整数，或留空。"].exists)
        XCTAssertFalse(app.buttons["保存"].isEnabled)
    }

    func testTextIntakeMarksFieldsClearsDateAndConfirmsDraft() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-reset", "-ui-testing-intake"]
        app.launch()

        let entry = app.buttons["inventory.aiIntake"]
        XCTAssertTrue(entry.waitForExistence(timeout: 10))
        entry.tap()

        let input = app.descendants(matching: .any)["intake.input"].firstMatch
        let parse = app.buttons["intake.parse"]
        guard input.waitForExistence(timeout: 10) else {
            XCTFail(app.debugDescription)
            return
        }
        input.tap()
        input.typeText("Two pounds of pork belly, a carton of eggs, and two bottles of milk")
        parse.tap()

        let milk = app.buttons["intake.candidate.cand_1a2b3c4d"]
        let confirm = app.buttons["intake.confirm"]
        XCTAssertTrue(milk.waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["intake.issues.cand_1a2b3c4d"].firstMatch.exists)
        XCTAssertFalse(confirm.isEnabled)
        capture("F5b intake review")

        milk.tap()
        let clearPurchaseDate = app.buttons["intake.clear.purchase_date"]
        XCTAssertTrue(clearPurchaseDate.waitForExistence(timeout: 10))
        capture("F5b intake editor")
        clearPurchaseDate.tap()
        XCTAssertFalse(clearPurchaseDate.exists)
        let expirationIssue = app.descendants(matching: .any)["intake.editor.issue.unopened_expiration_date"].firstMatch
        if !expirationIssue.isHittable { app.swipeUp() }
        XCTAssertTrue(expirationIssue.exists)
        app.buttons["保存草稿"].tap()

        input.tap()
        input.typeText("Review the draft again")
        parse.tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(
            format: "label CONTAINS %@", "已用清空购买日期的草稿重新解析"
        )).firstMatch.waitForExistence(timeout: 10))
        let adopt = app.buttons["intake.adopt.cand_1a2b3c4d"]
        if !adopt.isHittable { app.swipeUp() }
        adopt.tap()
        XCTAssertTrue(confirm.isEnabled)
        confirm.tap()

        XCTAssertTrue(app.staticTexts["物品已入库，补货条目之前已完成"].waitForExistence(timeout: 10))
        XCTAssertEqual(confirm.label, "确认入库（0）")
        XCTAssertFalse(confirm.isEnabled)
        XCTAssertFalse(milk.exists)
    }

    func testTextIntakeEntryIsHiddenWhenUnsupported() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-reset", "-ui-testing-intake", "-ui-testing-intake-unavailable"]
        app.launch()

        XCTAssertTrue(app.staticTexts["没有库存"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["inventory.aiIntake"].exists)
    }

    private func launchHouseholdSettings() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-testing-reset", "-ui-testing-household-settings"]
        app.launch()
        return app
    }

    private func openExplore(in app: XCUIApplication) {
        let explore = app.buttons["探索"]
        XCTAssertTrue(explore.waitForExistence(timeout: 5))
        explore.tap()
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testLiveConnectionWhenCredentialsProvided() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let url = environment["STOCK_MANAGER_UI_URL"], let token = environment["STOCK_MANAGER_UI_TOKEN"] else {
            throw XCTSkip("设置 STOCK_MANAGER_UI_URL 和 STOCK_MANAGER_UI_TOKEN 后运行真实后端冒烟测试")
        }
        let app = XCUIApplication(); app.launchArguments = ["-ui-testing-reset"]; app.launch()
        app.textFields["connection.url"].tap(); app.textFields["connection.url"].clearAndType(url)
        app.secureTextFields["connection.token"].tap(); app.secureTextFields["connection.token"].typeText(token)
        app.buttons["connection.submit"].tap()
        XCTAssertTrue(app.tabBars.buttons["首页"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.tabBars.buttons["库存"].exists)
        XCTAssertTrue(app.tabBars.buttons["补货"].exists)
        XCTAssertTrue(app.tabBars.buttons["菜谱"].exists)
        XCTAssertTrue(app.tabBars.buttons["设置"].exists)
    }
}

private extension XCUIElement {
    func clearAndType(_ text: String) {
        tap()
        if let current = value as? String { typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count)) }
        typeText(text)
    }
}
