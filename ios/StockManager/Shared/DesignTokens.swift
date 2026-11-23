import SwiftUI
import UIKit

enum AppSpacing {
    static let xSmall: CGFloat = 4
    static let small: CGFloat = 8
    static let medium: CGFloat = 12
    static let large: CGFloat = 16
    static let xLarge: CGFloat = 24
    static let page: CGFloat = large
}

enum AppRadius {
    static let card: CGFloat = 16
}

enum ThemePalette: String, CaseIterable, Identifiable {
    case native
    case okabeIto
    case tolMuted

    var id: String { rawValue }

    var name: String {
        switch self {
        case .native: "默认"
        case .okabeIto: "色盲友好"
        case .tolMuted: "低饱和"
        }
    }

    var accent: Color {
        switch self {
        case .native: .blue
        case .okabeIto: .adaptive(light: 0x0072B2, dark: 0x4FA9DD)
        case .tolMuted: .adaptive(light: 0x332288, dark: 0x8F80D8)
        }
    }

    var auxiliary: [Color] {
        switch self {
        case .native:
            [.blue, .green, .yellow, .pink, .orange, .purple]
        case .okabeIto:
            [
                .adaptive(light: 0x0072B2, dark: 0x4FA9DD),
                .adaptive(light: 0xE69F00, dark: 0xF2B94B),
                .adaptive(light: 0x56B4E9, dark: 0x78C8F0),
                .adaptive(light: 0x009E73, dark: 0x42C99B),
                .adaptive(light: 0xF0E442, dark: 0xF5EA70),
                .adaptive(light: 0xD55E00, dark: 0xF08A42),
                .adaptive(light: 0xCC79A7, dark: 0xE39BC2),
                .adaptive(light: 0x000000, dark: 0xBFBFBF)
            ]
        case .tolMuted:
            [
                .adaptive(light: 0x332288, dark: 0x8F80D8),
                .adaptive(light: 0xCC6677, dark: 0xF08FA0),
                .adaptive(light: 0xDDCC77, dark: 0xE7D991),
                .adaptive(light: 0x117733, dark: 0x5BD69A),
                .adaptive(light: 0x88CCEE, dark: 0xA8DDF5),
                .adaptive(light: 0x882255, dark: 0xD472A0),
                .adaptive(light: 0x44AA99, dark: 0x74CFBF),
                .adaptive(light: 0x999933, dark: 0xD0D06A),
                .adaptive(light: 0xAA4499, dark: 0xD77BC7)
            ]
        }
    }

    var statusActive: Color {
        switch self {
        case .native: .green
        case .okabeIto: .adaptive(light: 0x009E73, dark: 0x42C99B)
        case .tolMuted: .adaptive(light: 0x117733, dark: 0x5BD69A)
        }
    }

    var statusExpiring: Color {
        switch self {
        case .native: .orange
        case .okabeIto: .adaptive(light: 0xE69F00, dark: 0xF2B94B)
        case .tolMuted: .adaptive(light: 0x999933, dark: 0xD0D06A)
        }
    }

    var statusExpired: Color {
        switch self {
        case .native: .red
        case .okabeIto: .adaptive(light: 0xD55E00, dark: 0xF08A42)
        case .tolMuted: .adaptive(light: 0xCC6677, dark: 0xF08FA0)
        }
    }

    var statusConsumed: Color {
        switch self {
        case .native: .secondary
        case .okabeIto: .adaptive(light: 0x000000, dark: 0xBFBFBF)
        case .tolMuted: .adaptive(light: 0x332288, dark: 0x8F80D8)
        }
    }
}

@MainActor
@Observable
final class AppTheme {
    private static let storageKey = "appearance.themePalette"
    private let defaults: UserDefaults

    var palette: ThemePalette {
        didSet { defaults.set(palette.rawValue, forKey: Self.storageKey) }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let storedValue = defaults.string(forKey: Self.storageKey)
        palette = storedValue.flatMap(ThemePalette.init(rawValue:)) ?? .native
        if storedValue != nil, ThemePalette(rawValue: storedValue ?? "") == nil {
            defaults.set(ThemePalette.native.rawValue, forKey: Self.storageKey)
        }
    }

    var accent: Color { palette.accent }
    var categories: [Color] { palette.auxiliary }
    var statusActive: Color { palette.statusActive }
    var statusExpiring: Color { palette.statusExpiring }
    var statusExpired: Color { palette.statusExpired }
    var statusConsumed: Color { palette.statusConsumed }
    var foregroundOnAccent: Color { .white }

    func statusColor(_ status: ItemStatus) -> Color {
        switch status {
        case .active: statusActive
        case .expiringSoon: statusExpiring
        case .expired: statusExpired
        case .consumed: statusConsumed
        }
    }
}

extension Color {
    fileprivate static func adaptive(light: UInt32, dark: UInt32) -> Color {
        Color(UIColor { traits in
            UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light)
        })
    }
}

private extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xff) / 255,
            green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255,
            alpha: 1
        )
    }
}
