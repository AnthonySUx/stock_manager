import SwiftUI

@main
struct StockManagerApp: App {
    @State private var session = AppSession()
    @State private var theme = AppTheme()

    init() {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-ui-testing-reset") {
            let defaults = UserDefaults(suiteName: "com.stockmanager.native.uitests") ?? .standard
            defaults.removePersistentDomain(forName: "com.stockmanager.native.uitests")
            let tokenStore = KeychainTokenStore(service: "com.stockmanager.native.uitests", account: "test-token")
            let clean = AppSession(defaults: defaults, tokenStore: tokenStore)
            try? clean.disconnect()
            _session = State(initialValue: clean)
        }
        #endif
    }
    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(session)
                .environment(session.capabilities)
                .environment(theme)
                .tint(theme.accent)
                .task { await session.restoreAndValidate() }
        }
    }
}

private struct RootView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        content
            .task(id: session.connectionID) { await session.refreshCapabilities() }
            .onChange(of: scenePhase) { _, phase in
                guard phase == .active else { return }
                Task { await session.refreshCapabilities() }
            }
    }

    @ViewBuilder private var content: some View {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-ui-testing-consume") {
            ConsumeItemTestHost()
        } else if ProcessInfo.processInfo.arguments.contains("-ui-testing-explore") {
            ExploreUITestHost()
        } else if ProcessInfo.processInfo.arguments.contains("-ui-testing-household-settings") {
            HouseholdSettingsUITestHost()
        } else if ProcessInfo.processInfo.arguments.contains("-ui-testing-intake") {
            IntakeUITestHost()
        } else {
            sessionContent
        }
        #else
        sessionContent
        #endif
    }

    @ViewBuilder private var sessionContent: some View {
        switch session.state {
        case .connected(let connection):
            ConnectedAppView(client: connection.client).id(session.configuredURL)
        case .connecting(let previous):
            if let previous { ConnectedAppView(client: previous.client).id(session.configuredURL) }
            else { connectionProgress("正在验证服务器…") }
        case .restoring:
            connectionProgress("正在恢复安全连接…")
        case .disconnected:
            ConnectionView(initialURL: session.configuredURL)
        }
    }

    private func connectionProgress(_ message: String) -> some View {
        ContentUnavailableView { ProgressView() } description: { Text(message) }
    }
}
