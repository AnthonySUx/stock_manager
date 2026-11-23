import SwiftUI

struct LoadingView: View {
    @Environment(AppTheme.self) private var theme
    var text = "正在加载…"
    var body: some View { ProgressView(text).tint(theme.accent).frame(maxWidth: .infinity, maxHeight: .infinity) }
}

struct EmptyStateView: View {
    @Environment(AppTheme.self) private var theme
    let title: String; let message: String; var icon = "tray"
    var body: some View {
        ContentUnavailableView(title, systemImage: icon, description: Text(message)).tint(theme.accent)
    }
}

struct FailureView: View {
    @Environment(AppTheme.self) private var theme
    let message: String; let retry: () -> Void
    var body: some View {
        ContentUnavailableView {
            Label("加载失败", systemImage: "exclamationmark.triangle")
        } description: { Text(message) } actions: { Button("重试", action: retry).buttonStyle(PrimaryActionButtonStyle()) }
    }
}

struct StatusBadge: View {
    @Environment(AppTheme.self) private var theme
    let status: ItemStatus
    private var icon: String {
        switch status {
        case .active: "checkmark.circle"
        case .expiringSoon: "clock"
        case .expired: "exclamationmark.triangle"
        case .consumed: "checkmark.circle.fill"
        }
    }
    var body: some View {
        let color = theme.statusColor(status)
        HStack(spacing: AppSpacing.xSmall) {
            Image(systemName: icon).foregroundStyle(color)
            Text(status.title).foregroundStyle(.primary)
        }
            .font(.caption.weight(.semibold))
            .padding(.horizontal, AppSpacing.small)
            .padding(.vertical, AppSpacing.xSmall)
            .background(color.opacity(0.12), in: Capsule())
    }
}

struct ErrorAlert: ViewModifier {
    @Binding var message: String?
    func body(content: Content) -> some View {
        content.alert("操作失败", isPresented: Binding(get: { message != nil }, set: { if !$0 { message = nil } })) {
            Button("好", role: .cancel) { message = nil }
        } message: { Text(message ?? "") }
    }
}

extension View { func errorAlert(_ message: Binding<String?>) -> some View { modifier(ErrorAlert(message: message)) } }

struct SavingOverlay: ViewModifier {
    @Environment(AppTheme.self) private var theme
    let saving: Bool
    func body(content: Content) -> some View {
        content.overlay { if saving { ZStack { Color.primary.opacity(0.12).ignoresSafeArea(); ProgressView().tint(theme.accent).padding(AppSpacing.xLarge).background(.regularMaterial, in: RoundedRectangle(cornerRadius: AppRadius.card)) } } }
    }
}

struct AppCard<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(AppSpacing.large)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: AppRadius.card))
    }
}

struct PrimaryActionButtonStyle: ButtonStyle {
    @Environment(AppTheme.self) private var theme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(theme.foregroundOnAccent)
            .padding(.horizontal, AppSpacing.large)
            .padding(.vertical, AppSpacing.medium)
            .background(theme.accent.opacity(configuration.isPressed ? 0.78 : 1), in: RoundedRectangle(cornerRadius: AppRadius.card))
    }
}
extension View { func savingOverlay(_ saving: Bool) -> some View { modifier(SavingOverlay(saving: saving)) } }

struct LabeledValue: View {
    let label: String; let value: String
    var body: some View { LabeledContent(label) { Text(value).foregroundStyle(.secondary) } }
}

private struct RefreshableWithCapabilities: ViewModifier {
    @Environment(AppSession.self) private var session: AppSession?
    let action: @Sendable () async -> Void

    func body(content: Content) -> some View {
        content.refreshable {
            async let refresh: Void? = session?.refreshCapabilities()
            await action()
            _ = await refresh
        }
    }
}

extension View {
    func refreshableWithCapabilities(_ action: @escaping @Sendable () async -> Void) -> some View {
        modifier(RefreshableWithCapabilities(action: action))
    }
}
