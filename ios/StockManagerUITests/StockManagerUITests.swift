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
