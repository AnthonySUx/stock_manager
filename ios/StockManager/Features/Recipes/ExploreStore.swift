import Foundation
import Observation

enum ExploreOperation {
    case generate(ExploreRequest)
    case expand(ExploreIdea)
}

struct ExploreResults: Equatable {
    let ideas: [ExploreIdea]
    var completion: ExploreStreamCompletion?
    var warnings: [AIWarning] { completion?.warnings ?? [] }
}

enum ExploreState {
    case idle
    case generating(previous: ExploreResults?, ideas: [ExploreIdea])
    case expanding(ExploreResults?)
    case loaded(ExploreResults)
    case failed(previous: ExploreResults?, message: String, retry: ExploreOperation?)

    var results: ExploreResults? {
        switch self {
        case .idle: nil
        case .generating(let previous, let ideas): ideas.isEmpty ? previous : ExploreResults(ideas: ideas)
        case .expanding(let previous), .failed(let previous, _, _): previous
        case .loaded(let results): results
        }
    }

    var isLoading: Bool {
        switch self {
        case .generating, .expanding: true
        default: false
        }
    }

    var isGenerating: Bool {
        if case .generating = self { true } else { false }
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
        guard isAvailable, !state.isLoading, !Task.isCancelled else { return nil }
        let previous = state.results

        do {
            switch operation {
            case .generate(let request):
                state = .generating(previous: previous, ideas: [])
                try await generate(request, previous: previous)
            case .expand(let idea):
                state = .expanding(previous)
                let response = try await client.expand(idea)
                try Task.checkCancellation()
                state = previous.map(ExploreState.loaded) ?? .idle
                return response
            }
        } catch {
            let retained = state.results
            let restored = retained.map(ExploreState.loaded) ?? .idle
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled {
                state = restored
            } else if case .server(503, "ai_unavailable", _, _) = error as? APIClientError {
                state = restored
                await capabilities.refreshAfterTextUnavailable(using: client)
            } else {
                let retry: ExploreOperation?
                if case .server(502, "ai_upstream_error", _, _) = error as? APIClientError {
                    retry = operation
                } else if case .generate = operation, error is URLError || (error as? APIClientError) == .incompleteStream {
                    retry = operation
                } else {
                    retry = nil
                }
                state = .failed(previous: retained, message: error.localizedDescription, retry: retry)
            }
        }
        return nil
    }

    private func generate(_ request: ExploreRequest, previous: ExploreResults?) async throws {
        var ideas: [ExploreIdea] = []
        for try await event in client.exploreStream(request) {
            try Task.checkCancellation()
            switch event {
            case .idea(let idea):
                ideas.append(idea)
                state = .generating(previous: previous, ideas: ideas)
            case .done(let completion):
                state = .loaded(ExploreResults(ideas: ideas, completion: completion))
                return
            case .error(let code):
                state = .failed(previous: state.results,
                                message: DisplayText.error(code) ?? "创意生成失败，请重试",
                                retry: .generate(request))
                return
            }
        }
        try Task.checkCancellation()
        throw APIClientError.incompleteStream
    }
}
