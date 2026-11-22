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
