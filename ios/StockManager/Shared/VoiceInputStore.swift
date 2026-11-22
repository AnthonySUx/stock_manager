import Foundation
import Observation

@MainActor @Observable
final class VoiceInputStore {
    let recorder = VoiceRecorder()
    private(set) var action: ActionState = .idle
    private(set) var isTranscribing = false
    private(set) var permissionDenied = false
    @ObservationIgnored private var task: Task<Void, Never>?

    func start(client: any APIClientProtocol, capabilities: CapabilitiesStore, feature: SpeechFeature,
               onTranscript: @escaping (String) -> Void) {
        guard !action.isRunning else { return }
        action = .running
        permissionDenied = false
        task = Task {
            defer { task = nil }
            let recording: URL
            do {
                recording = try await recorder.record()
            } catch {
                permissionDenied = (error as? VoiceRecorder.Failure) == .permissionDenied && !Task.isCancelled
                action = Task.isCancelled ? .idle : .failed(error.localizedDescription)
                return
            }
            await transcribe(recording, client: client, capabilities: capabilities, feature: feature,
                             onTranscript: onTranscript)
        }
    }

    /// Uploads a finished recording and publishes the result. Internal so tests can skip the microphone.
    func transcribe(_ recording: URL, client: any APIClientProtocol, capabilities: CapabilitiesStore,
                    feature: SpeechFeature, onTranscript: (String) -> Void) async {
        action = .running
        isTranscribing = true
        defer { isTranscribing = false }
        do {
            let result = try await Self.transcribeRecording(at: recording, client: client, feature: feature)
            try Task.checkCancellation()
            guard let transcript = result.transcript.nilIfBlank else {
                action = .failed("未识别到语音，请重试")
                return
            }
            onTranscript(transcript)
            action = .succeeded(nil)
        } catch {
            if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled {
                action = .idle
                return
            }
            action = .failed(error.localizedDescription)
            // Hide the microphone once the server reports speech as disabled.
            if case .server(503, "asr_unavailable", _, _) = error as? APIClientError {
                await capabilities.refreshAfterSpeechUnavailable(using: client)
            }
        }
    }

    func cancel() { task?.cancel() }

    static func transcribeRecording(at url: URL, client: any APIClientProtocol,
                                    feature: SpeechFeature) async throws -> SpeechTranscription {
        defer { try? FileManager.default.removeItem(at: url) }
        try Task.checkCancellation()
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size <= 8_388_608 else {
            throw APIClientError.server(status: 413, code: "audio_too_large", params: [:], fallback: "")
        }
        let data = try Data(contentsOf: url, options: .mappedIfSafe)
        return try await client.transcribeSpeech(data, feature: feature)
    }
}

extension String {
    mutating func appendVoiceTranscript(_ transcript: String) {
        self = trimmed.isEmpty ? transcript : self + "\n" + transcript
    }
}
