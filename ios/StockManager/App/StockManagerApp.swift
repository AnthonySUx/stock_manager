import SwiftUI

@main
struct StockManagerApp: App {
    @State private var session = AppSession()

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
            RootView().environment(session).task { await session.restoreAndValidate() }
        }
    }
}

private struct RootView: View {
    @Environment(AppSession.self) private var session
    var body: some View {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-ui-testing-consume") {
            ConsumeItemTestHost()
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
