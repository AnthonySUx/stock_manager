import Foundation
import Observation

@MainActor @Observable
final class VoiceInputStore {
    let recorder = VoiceRecorder()
    private(set) var action: ActionState = .idle
    private(set) var isTranscribing = false
    private(set) var permissionDenied = false
    @ObservationIgnored private var task: Task<Void, Never>?

    func start(client: any APIClientProtocol, feature: SpeechFeature, onTranscript: @escaping (String) -> Void) {
        guard !action.isRunning else { return }
        action = .running
        permissionDenied = false
        task = Task {
            defer {
                task = nil
                isTranscribing = false
            }
            do {
                let recording = try await recorder.record()
                isTranscribing = true
                let result = try await Self.transcribeRecording(at: recording, client: client, feature: feature)
                try Task.checkCancellation()
                guard let transcript = result.transcript.nilIfBlank else {
                    action = .failed("未识别到语音，请重试")
                    return
                }
                onTranscript(transcript)
                action = .succeeded(nil)
            } catch {
                permissionDenied = (error as? VoiceRecorder.Failure) == .permissionDenied && !Task.isCancelled
                action = Task.isCancelled ? .idle : .failed(error.localizedDescription)
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
