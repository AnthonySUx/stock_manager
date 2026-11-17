import SwiftUI

struct ConnectionView: View {
    @Environment(AppSession.self) private var session
    @State private var urlText: String
    @State private var token = ""
    @State private var action: ActionState = .idle

    init(initialURL: String) { _urlText = State(initialValue: initialURL) }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://服务器:8000/api", text: $urlText)
                        .textInputAutocapitalization(.never).keyboardType(.URL)
                        .accessibilityIdentifier("connection.url")
                    SecureField("共享 API 令牌", text: $token)
                        .textInputAutocapitalization(.never).privacySensitive()
                        .accessibilityIdentifier("connection.token")
                } header: { Text("连接家庭服务器") } footer: {
                    Text("地址保存在本机偏好设置中；令牌只保存在系统 Keychain，不会写入日志。未填写 /api 时会自动补全。")
                }
                Section {
                    Button { Task { await connect() } } label: {
                        HStack { Spacer(); if action.isRunning { ProgressView() } else { Text("测试并连接").fontWeight(.semibold) }; Spacer() }
                    }.disabled(urlText.trimmed.isEmpty || token.trimmed.isEmpty || action.isRunning)
                        .accessibilityIdentifier("connection.submit")
                }
                if let existing = session.connectionError {
                    Section("上次连接") { Label(existing, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
                }
            }
            .navigationTitle("欢迎")
            .actionErrorAlert($action)
            .savingOverlay(action.isRunning)
        }
    }

    private func connect() async {
        action = .running
        do { try await session.connect(urlText: urlText, token: token); action = .succeeded(nil) }
        catch { action = .failed(error.localizedDescription) }
    }
}
