import Foundation
import Observation
import Security

protocol SecureTokenStoring {
    func read() throws -> String?
    func save(_ token: String) throws
    func remove() throws
}

enum KeychainError: LocalizedError {
    case unexpectedStatus(OSStatus)
    var errorDescription: String? { "无法访问安全凭据（\(Self.self)：\(status)）" }
    private var status: OSStatus { if case .unexpectedStatus(let value) = self { value } else { 0 } }
}

struct KeychainTokenStore: SecureTokenStoring {
    let service: String
    let account: String

    init(service: String = "com.stockmanager.native.api", account: String = "household-token") {
        self.service = service; self.account = account
    }

    func read() throws -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw KeychainError.unexpectedStatus(status) }
        return (result as? Data).flatMap { String(data: $0, encoding: .utf8) }
    }

    func save(_ token: String) throws {
        let data = Data(token.utf8)
        let status = SecItemUpdate(baseQuery as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var query = baseQuery; query[kSecValueData as String] = data
            query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let addStatus = SecItemAdd(query as CFDictionary, nil)
            guard addStatus == errSecSuccess else { throw KeychainError.unexpectedStatus(addStatus) }
        } else if status != errSecSuccess {
            throw KeychainError.unexpectedStatus(status)
        }
    }

    func remove() throws {
        let status = SecItemDelete(baseQuery as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw KeychainError.unexpectedStatus(status) }
    }

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
    }
}

@MainActor @Observable
final class AppSession {
    private let defaults: UserDefaults
    private let tokenStore: SecureTokenStoring
    private(set) var state: AppSessionState = .disconnected(lastError: nil)

    var client: (any APIClientProtocol)? {
        switch state { case .connected(let connection): connection.client; case .connecting(let previous): previous?.client; default: nil }
    }
    var health: HealthResponse? {
        switch state { case .connected(let connection): connection.health; case .connecting(let previous): previous?.health; default: nil }
    }
    var connectionError: String? { if case .disconnected(let error) = state { error } else { nil } }
    var isConnected: Bool { client != nil }
    var configuredURL: String { defaults.string(forKey: Keys.url) ?? "http://localhost:8000/api" }

    init(defaults: UserDefaults = .standard, tokenStore: SecureTokenStoring = KeychainTokenStore()) {
        self.defaults = defaults; self.tokenStore = tokenStore
        if let token = try? tokenStore.read(), !token.isEmpty,
           let url = Self.normalizedURL(defaults.string(forKey: Keys.url) ?? "") {
            state = .restoring(APIClient(baseURL: url, token: token))
        }
    }

    func restoreAndValidate() async {
        guard case .restoring(let client) = state else { return }
        do { let health = try await client.health(); _ = try await client.settings(); state = .connected(.init(client: client, health: health)) }
        catch { state = .disconnected(lastError: error.localizedDescription) }
    }

    func connect(urlText: String, token: String) async throws {
        guard let url = Self.normalizedURL(urlText) else { throw APIClientError.invalidURL }
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw APIClientError.unauthorized }
        let candidate = APIClient(baseURL: url, token: trimmed)
        let previous: SessionConnection? = if case .connected(let connection) = state { connection } else { nil }
        state = .connecting(previous: previous)
        do {
            let status = try await candidate.health()
            _ = try await candidate.settings()
            try tokenStore.save(trimmed)
            defaults.set(url.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")), forKey: Keys.url)
            state = .connected(.init(client: candidate, health: status))
        } catch {
            state = previous.map(AppSessionState.connected) ?? .disconnected(lastError: error.localizedDescription)
            throw error
        }
    }

    func disconnect() throws {
        try tokenStore.remove(); state = .disconnected(lastError: nil)
    }

    static func normalizedURL(_ text: String) -> URL? {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard var components = URLComponents(string: clean), ["http", "https"].contains(components.scheme?.lowercased()), components.host != nil else { return nil }
        if components.path.isEmpty { components.path = "/api" }
        return components.url
    }

    private enum Keys { static let url = "connection.apiBaseURL" }
}

enum AppSessionState {
    case disconnected(lastError: String?)
    case restoring(APIClient)
    case connecting(previous: SessionConnection?)
    case connected(SessionConnection)
}

struct SessionConnection {
    let client: any APIClientProtocol
    let health: HealthResponse
}
