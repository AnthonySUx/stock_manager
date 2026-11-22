import Foundation

enum APIClientError: LocalizedError, Equatable {
    case invalidURL
    case invalidResponse
    case incompleteStream
    case unauthorized
    case server(status: Int, code: String?, params: [String: JSONValue], fallback: String)
    case invalidMultipart
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "服务器地址无效"
        case .invalidResponse: "服务器返回了无效响应"
        case .incompleteStream: "创意接收中断，请重试"
        case .unauthorized: "API 令牌无效或缺失"
        case .server(_, let code, let params, let fallback): code.flatMap { DisplayText.error($0, params: params) } ?? fallback
        case .invalidMultipart: "上传文件的表单名称、文件名或类型无效"
        case .decoding(let message): "无法解析服务器数据：\(message)"
        }
    }
}

struct ItemFilters: Equatable {
    var categoryId: Int?; var owner: String?; var location: String?; var status: ItemStatus?
}

struct MultipartFile: Sendable {
    let field: String
    let filename: String
    let contentType: String
    let data: Data
}

protocol APIClientProtocol: Sendable {
    func health() async throws -> HealthResponse
    func capabilities() async throws -> Capabilities
    func settings() async throws -> AppSettings
    func updateSettings(days: Int) async throws -> AppSettings
    func sendMultipart<Response: Decodable>(path: String, fields: [String: String], files: [MultipartFile], timeout: TimeInterval) async throws -> Response

    func items(filters: ItemFilters) async throws -> [StockItem]
    func searchItems(_ keyword: String, filters: ItemFilters) async throws -> [StockItem]
    func item(id: Int) async throws -> StockItem
    func reminders() async throws -> [StockItem]
    func createItem(_ body: ItemCreate) async throws -> StockItem
    func updateItem(id: Int, _ body: ItemUpdate) async throws -> StockItem
    func consumeItem(id: Int, _ body: ConsumeRequest) async throws -> StockItem
    func deleteItem(id: Int) async throws
    func cleanItems(statuses: [ItemStatus]) async throws -> String

    func categories(tree: Bool) async throws -> [Category]
    func createCategory(_ body: CategoryCreate) async throws -> Category
    func updateCategory(id: Int, _ body: CategoryUpdate) async throws -> Category
    func deleteCategory(id: Int) async throws

    func restockItems(status: String?) async throws -> [RestockItem]
    func createRestock(_ body: RestockCreate) async throws -> RestockItem
    func updateRestock(id: Int, _ body: RestockUpdate) async throws -> RestockItem
    func completeRestock(id: Int, _ body: RestockDone) async throws -> String
    func deleteRestock(id: Int) async throws
    func cleanRestock() async throws -> String

    func recipes(query: String?, source: String?, category: String?, favoritesOnly: Bool, limit: Int, offset: Int) async throws -> [RecipeSummary]
    func recipe(id: Int) async throws -> Recipe
    func createRecipe(_ body: RecipeWrite) async throws -> Recipe
    func updateRecipe(id: Int, _ body: RecipeWrite) async throws -> Recipe
    func deleteRecipe(id: Int) async throws
    func forkRecipe(id: Int) async throws -> Recipe
    func setFavorite(id: Int, favorite: Bool) async throws
    func recommendations(scene: String) async throws -> RecommendationResponse
    func recipeSources() async throws -> [SourceInfo]
    func consumePreview(recipeId: Int) async throws -> ConsumePreview
    func cook(recipeId: Int, _ body: CookRequest) async throws -> CookResponse
    func explore(_ body: ExploreRequest) async throws -> ExploreResponse
    func exploreStream(_ body: ExploreRequest) -> AsyncThrowingStream<ExploreStreamEvent, Error>
    func expand(_ idea: ExploreIdea) async throws -> ExpandResponse
}

struct APIClient: APIClientProtocol {
    let baseURL: URL
    let token: String
    var session: URLSession = .shared

    func health() async throws -> HealthResponse { try await send("health", authenticated: false) }
    func capabilities() async throws -> Capabilities { try await send("capabilities") }
    func settings() async throws -> AppSettings { try await send("settings") }
    func updateSettings(days: Int) async throws -> AppSettings {
        try await send("settings", method: "PATCH", body: SettingsUpdate(expirationReminderDays: String(days)))
    }

    func items(filters: ItemFilters = .init()) async throws -> [StockItem] {
        try await send("items", query: filterQuery(filters))
    }
    func searchItems(_ keyword: String, filters: ItemFilters = .init()) async throws -> [StockItem] {
        try await send("items/search", query: [URLQueryItem(name: "keyword", value: keyword)] + filterQuery(filters))
    }
    func item(id: Int) async throws -> StockItem { try await send("items/\(id)") }
    func reminders() async throws -> [StockItem] { try await send("items/reminders") }
    func createItem(_ body: ItemCreate) async throws -> StockItem { try await send("items", method: "POST", body: body) }
    func updateItem(id: Int, _ body: ItemUpdate) async throws -> StockItem { try await send("items/\(id)", method: "PATCH", body: body) }
    func consumeItem(id: Int, _ body: ConsumeRequest) async throws -> StockItem { try await send("items/\(id)/consume", method: "POST", body: body) }
    func deleteItem(id: Int) async throws { let _: MessageResponse = try await send("items/\(id)", method: "DELETE") }
    func cleanItems(statuses: [ItemStatus]) async throws -> String {
        let response: MessageResponse = try await send("items/clean", method: "POST", query: statuses.map { .init(name: "statuses", value: $0.rawValue) })
        return response.message
    }

    func categories(tree: Bool) async throws -> [Category] { try await send(tree ? "categories" : "categories/flat") }
    func createCategory(_ body: CategoryCreate) async throws -> Category { try await send("categories", method: "POST", body: body) }
    func updateCategory(id: Int, _ body: CategoryUpdate) async throws -> Category { try await send("categories/\(id)", method: "PATCH", body: body) }
    func deleteCategory(id: Int) async throws { let _: MessageResponse = try await send("categories/\(id)", method: "DELETE") }

    func restockItems(status: String? = nil) async throws -> [RestockItem] {
        try await send("restock", query: status.map { [.init(name: "status", value: $0)] } ?? [])
    }
    func createRestock(_ body: RestockCreate) async throws -> RestockItem { try await send("restock", method: "POST", body: body) }
    func updateRestock(id: Int, _ body: RestockUpdate) async throws -> RestockItem { try await send("restock/\(id)", method: "PATCH", body: body) }
    func completeRestock(id: Int, _ body: RestockDone) async throws -> String {
        let response: MessageResponse = try await send("restock/\(id)/done", method: "POST", body: body); return response.message
    }
    func deleteRestock(id: Int) async throws { let _: MessageResponse = try await send("restock/\(id)", method: "DELETE") }
    func cleanRestock() async throws -> String {
        let response: MessageResponse = try await send("restock/clean", method: "POST"); return response.message
    }

    func recipes(query: String?, source: String?, category: String?, favoritesOnly: Bool, limit: Int = 20, offset: Int = 0) async throws -> [RecipeSummary] {
        var params = [URLQueryItem(name: "limit", value: String(limit)), .init(name: "offset", value: String(offset))]
        if let query, !query.isEmpty { params.append(.init(name: "query", value: query)) }
        if let source { params.append(.init(name: "source_type", value: source)) }
        if let category { params.append(.init(name: "category", value: category)) }
        if favoritesOnly { params.append(.init(name: "favorite_only", value: "true")) }
        return try await send("recipes", query: params)
    }
    func recipe(id: Int) async throws -> Recipe { try await send("recipes/\(id)") }
    func createRecipe(_ body: RecipeWrite) async throws -> Recipe { try await send("recipes", method: "POST", body: body) }
    func updateRecipe(id: Int, _ body: RecipeWrite) async throws -> Recipe { try await send("recipes/\(id)", method: "PATCH", body: body) }
    func deleteRecipe(id: Int) async throws { let _: MessageResponse = try await send("recipes/\(id)", method: "DELETE") }
    func forkRecipe(id: Int) async throws -> Recipe { try await send("recipes/\(id)/fork", method: "POST") }
    func setFavorite(id: Int, favorite: Bool) async throws {
        let _: MessageResponse = try await send("recipes/\(id)/favorite", method: favorite ? "POST" : "DELETE")
    }
    func recommendations(scene: String) async throws -> RecommendationResponse {
        try await send("recipes/recommendations", query: [.init(name: "scene", value: scene)])
    }
    func recipeSources() async throws -> [SourceInfo] { try await send("recipes/sources") }
    func consumePreview(recipeId: Int) async throws -> ConsumePreview { try await send("recipes/\(recipeId)/consume-preview") }
    func cook(recipeId: Int, _ body: CookRequest) async throws -> CookResponse { try await send("recipes/\(recipeId)/cook", method: "POST", body: body) }
    func explore(_ body: ExploreRequest) async throws -> ExploreResponse {
        try await send("recipes/explore", method: "POST", body: body, timeout: 120)
    }
    func exploreStream(_ body: ExploreRequest) -> AsyncThrowingStream<ExploreStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let producer = Task {
                do {
                    try await readExploreStream(body, into: continuation)
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in producer.cancel() }
        }
    }

    private func readExploreStream(
        _ body: ExploreRequest,
        into continuation: AsyncThrowingStream<ExploreStreamEvent, Error>.Continuation
    ) async throws {
        let path = "recipes/explore/stream"
        let method = "POST"
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let request = try makeRequest(path, method: method, query: [], authenticated: true,
                                      bodyData: encoder.encode(body), contentType: "application/json",
                                      accept: "text/event-stream", timeout: 120)
        let (bytes, response) = try await session.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        if http.statusCode == 401 { throw APIClientError.unauthorized }
        guard 200..<300 ~= http.statusCode else {
            var data = Data()
            for try await byte in bytes { data.append(byte) }
            throw Self.serverError(data, status: http.statusCode, method: method, path: path)
        }
        guard http.mimeType == "text/event-stream" else { throw APIClientError.invalidResponse }

        var parser = ExploreStreamParser()
        for try await byte in bytes {
            if let event = try parser.receive(byte) {
                try Task.checkCancellation()
                if case .terminated = continuation.yield(event) { return }
                if event.isTerminal { return }
            }
        }
        try Task.checkCancellation()
        if let event = try parser.finish() {
            if case .terminated = continuation.yield(event) { return }
            if event.isTerminal { return }
        }
        throw APIClientError.incompleteStream
    }
    func expand(_ idea: ExploreIdea) async throws -> ExpandResponse {
        try await send("recipes/explore/expand", method: "POST", body: ExpandRequest(idea: idea), timeout: 120)
    }

    private func filterQuery(_ filters: ItemFilters) -> [URLQueryItem] {
        var result: [URLQueryItem] = []
        if let value = filters.categoryId { result.append(.init(name: "category", value: String(value))) }
        if let value = filters.owner, !value.isEmpty { result.append(.init(name: "owner", value: value)) }
        if let value = filters.location, !value.isEmpty { result.append(.init(name: "location", value: value)) }
        if let value = filters.status { result.append(.init(name: "status", value: value.rawValue)) }
        return result
    }

    private func send<Response: Decodable>(_ path: String, method: String = "GET", query: [URLQueryItem] = [], authenticated: Bool = true, timeout: TimeInterval = 15) async throws -> Response {
        try await send(path, method: method, query: query, authenticated: authenticated, bodyData: nil, timeout: timeout)
    }
    private func send<Response: Decodable, Body: Encodable>(_ path: String, method: String, query: [URLQueryItem] = [], authenticated: Bool = true, body: Body, timeout: TimeInterval = 15) async throws -> Response {
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        return try await send(path, method: method, query: query, authenticated: authenticated, bodyData: encoder.encode(body), timeout: timeout)
    }
    func sendMultipart<Response: Decodable>(path: String, fields: [String: String], files: [MultipartFile], timeout: TimeInterval) async throws -> Response {
        let boundary = UUID().uuidString
        var body = Data()

        for (field, value) in fields.sorted(by: { $0.key < $1.key }) {
            let name = try Self.multipartParameter(field)
            body.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8)
        }
        for file in files {
            let name = try Self.multipartParameter(file.field)
            let filename = try Self.multipartParameter(file.filename)
            guard !file.contentType.isEmpty, !file.contentType.contains(where: \.isNewline) else {
                throw APIClientError.invalidMultipart
            }
            body.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n".utf8)
            body.append(contentsOf: "Content-Type: \(file.contentType)\r\n\r\n".utf8)
            body.append(file.data)
            body.append(contentsOf: "\r\n".utf8)
        }
        body.append(contentsOf: "--\(boundary)--\r\n".utf8)

        return try await send(path, method: "POST", query: [], bodyData: body,
                              contentType: "multipart/form-data; boundary=\(boundary)", timeout: timeout)
    }

    private static func multipartParameter(_ value: String) throws -> String {
        guard !value.isEmpty, !value.contains(where: \.isNewline) else { throw APIClientError.invalidMultipart }
        return value.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"")
    }

    private func send<Response: Decodable>(_ path: String, method: String, query: [URLQueryItem], authenticated: Bool = true, bodyData: Data?, contentType: String = "application/json", timeout: TimeInterval = 15) async throws -> Response {
        let request = try makeRequest(path, method: method, query: query, authenticated: authenticated,
                                      bodyData: bodyData, contentType: contentType, accept: "application/json", timeout: timeout)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        if http.statusCode == 401 { throw APIClientError.unauthorized }
        guard 200..<300 ~= http.statusCode else {
            throw Self.serverError(data, status: http.statusCode, method: method, path: path)
        }
        do {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIClientError.decoding(error.localizedDescription)
        }
    }

    private func makeRequest(_ path: String, method: String, query: [URLQueryItem], authenticated: Bool,
                             bodyData: Data?, contentType: String, accept: String, timeout: TimeInterval) throws -> URLRequest {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        if !query.isEmpty { components?.queryItems = query }
        guard let url = components?.url else { throw APIClientError.invalidURL }
        var request = URLRequest(url: url); request.httpMethod = method; request.timeoutInterval = timeout
        request.setValue(accept, forHTTPHeaderField: "Accept")
        if bodyData != nil { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        if authenticated { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = bodyData
        return request
    }

    static func serverError(_ data: Data, status: Int, method: String, path: String) -> APIClientError {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let body = try? decoder.decode(APIErrorBody.self, from: data)
        let isRestockDone = method == "POST" && path.hasPrefix("restock/") && path.hasSuffix("/done")
        let fallback = if status == 409 && body?.code == nil && isRestockDone {
            DisplayText.restockAlreadyDone
        } else {
            body?.detail?.message ?? "请求失败（\(status)）"
        }
        return .server(status: status, code: body?.code, params: body?.params ?? [:], fallback: fallback)
    }
}

