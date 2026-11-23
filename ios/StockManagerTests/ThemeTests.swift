import XCTest
import SwiftUI
import UIKit
@testable import StockManager

@MainActor
final class ThemeTests: XCTestCase {
    func testThreePublishedPalettesAreAvailable() {
        XCTAssertEqual(ThemePalette.allCases.count, 3)
        XCTAssertEqual(ThemePalette.allCases.map(\.name), ["默认", "色盲友好", "低饱和"])
        XCTAssertTrue(ThemePalette.allCases.allSatisfy { $0.auxiliary.count >= 6 })
        XCTAssertTrue(ThemePalette.allCases.allSatisfy {
            $0.auxiliary.first.map(resolvedRGBA) == resolvedRGBA($0.accent)
        })
    }

    func testPaletteSelectionPersistsAcrossThemeInstances() throws {
        let suite = "ThemeTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        let first = AppTheme(defaults: defaults)
        XCTAssertEqual(first.palette, .native)
        first.palette = .tolMuted

        let restored = AppTheme(defaults: defaults)
        XCTAssertEqual(restored.palette, .tolMuted)
    }

    func testRemovedVibrantSelectionMigratesToNative() throws {
        let suite = "ThemeTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set("vibrant", forKey: "appearance.themePalette")

        let theme = AppTheme(defaults: defaults)

        XCTAssertEqual(theme.palette, .native)
        XCTAssertEqual(defaults.string(forKey: "appearance.themePalette"), ThemePalette.native.rawValue)
    }

    private func resolvedRGBA(_ color: Color) -> [CGFloat] {
        let resolved = UIColor(color).resolvedColor(with: UITraitCollection(userInterfaceStyle: .light))
        var red: CGFloat = 0
        var green: CGFloat = 0
        var blue: CGFloat = 0
        var alpha: CGFloat = 0
        resolved.getRed(&red, green: &green, blue: &blue, alpha: &alpha)
        return [red, green, blue, alpha]
    }
}
