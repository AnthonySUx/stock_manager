import Foundation
import Observation

enum ExploreOperation {
    case generate(ExploreRequest)
    case expand(ExploreIdea)
}

enum ExploreState {
    case idle
    case loading(previous: ExploreResponse?)
    case loaded(ExploreResponse)
    case failed(previous: ExploreResponse?, message: String, retry: ExploreOperation?)

    var response: ExploreResponse? {
        switch self {
        case .idle: nil
        case .loading(let previous), .failed(let previous, _, _): previous
        case .loaded(let response): response
        }
    }

    var isLoading: Bool {
        if case .loading = self { true } else { false }
    }
}

@MainActor @Observable
final class ExploreStore {
    private let client: any APIClientProtocol
    private let capabilities: CapabilitiesStore
    private(set) var state: ExploreState = .idle

    init(client: any APIClientProtocol, capabilities: CapabilitiesStore) {
        self.client = client
        self.capabilities = capabilities
    }

    var isAvailable: Bool { capabilities.value.ai.text }

    func perform(_ operation: ExploreOperation) async -> ExpandResponse? {
        guard isAvailable, !state.isLoading else { return nil }
        let previous = state.response
        let restored = previous.map(ExploreState.loaded) ?? .idle
        state = .loading(previous: previous)

        do {
            switch operation {
            case .generate(let request):
                let response = try await client.explore(request)
                try Task.checkCancellation()
                state = .loaded(response)
            case .expand(let idea):
                let response = try await client.expand(idea)
                try Task.checkCancellation()
                state = restored
                return response
            }
        } catch {
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled {
                state = restored
            } else if case .server(503, "ai_unavailable", _, _) = error as? APIClientError {
                state = restored
                await capabilities.refreshAfterTextUnavailable(using: client)
            } else {
                let retry: ExploreOperation?
                if case .server(502, "ai_upstream_error", _, _) = error as? APIClientError {
                    retry = operation
                } else {
                    retry = nil
                }
                state = .failed(previous: previous, message: error.localizedDescription, retry: retry)
            }
        }
        return nil
    }
}
