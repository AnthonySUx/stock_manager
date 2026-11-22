import Foundation
import Observation

@MainActor @Observable
final class CapabilitiesStore {
    private(set) var value = Capabilities.unavailable
    private(set) var phase: LoadPhase = .idle
    @ObservationIgnored private var generation = 0

    func refresh(using client: any APIClientProtocol) async {
        guard phase != .loading else { return }
        let previous = phase
        let request = generation
        phase = .loading

        do {
            let response = try await client.capabilities()
            try Task.checkCancellation()
            guard generation == request else { return }
            value = response
            phase = .loaded
        } catch {
            guard generation == request else { return }
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled {
                phase = previous
            } else {
                value = .unavailable
                phase = .failed(error.localizedDescription)
            }
        }
    }

    func reset() {
        // A request from a previous connection must not publish flags for the new server.
        generation += 1
        value = .unavailable
        phase = .idle
    }
}
