import AVFoundation
import Observation

@MainActor @Observable
final class VoiceRecorder: NSObject, AVAudioRecorderDelegate {
    /// The backend rejects audio longer than 120 seconds. AVAudioRecorder can write one
    /// extra buffer when it stops, so recording ends one second early.
    static let durationLimit: TimeInterval = 119
    static let sampleRate = 16_000
    static let settings: [String: Any] = [
        AVFormatIDKey: kAudioFormatLinearPCM,
        AVSampleRateKey: sampleRate,
        AVNumberOfChannelsKey: 1,
        AVLinearPCMBitDepthKey: 16,
        AVLinearPCMIsBigEndianKey: false,
        AVLinearPCMIsFloatKey: false
    ]

    enum Failure: LocalizedError {
        case permissionDenied, recordingFailed
        var errorDescription: String? {
            switch self {
            case .permissionDenied: "无法使用麦克风。请在系统设置中允许录音。"
            case .recordingFailed: "录音未能完成，请重试"
            }
        }
    }

    private(set) var isRecording = false
    private(set) var remainingSeconds = Int(durationLimit)
    private(set) var level: Double = 0
    @ObservationIgnored private var recorder: AVAudioRecorder?
    @ObservationIgnored private var completion: CheckedContinuation<Void, any Error>?
    @ObservationIgnored private var metering: Task<Void, Never>?

    func record() async throws -> URL {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-ui-testing-voice-fixture") {
            return try VoiceRecordingFixture.make()
        }
        #endif
        guard await AVAudioApplication.requestRecordPermission() else { throw Failure.permissionDenied }
        try Task.checkCancellation()

        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension("wav")
        let session = AVAudioSession.sharedInstance()
        var sessionActive = false
        var keepFile = false
        defer {
            metering?.cancel()
            metering = nil
            recorder?.delegate = nil
            recorder?.stop()
            recorder = nil
            isRecording = false
            if sessionActive { try? session.setActive(false, options: .notifyOthersOnDeactivation) }
            if !keepFile { try? FileManager.default.removeItem(at: url) }
        }

        do {
            try session.setCategory(.record)
            try session.setActive(true)
            sessionActive = true
            recorder = try AVAudioRecorder(url: url, settings: Self.settings)
        } catch {
            throw Failure.recordingFailed
        }
        guard let recorder else { throw Failure.recordingFailed }
        recorder.delegate = self
        recorder.isMeteringEnabled = true
        remainingSeconds = Int(Self.durationLimit)
        level = 0
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                completion = continuation
                guard !Task.isCancelled else {
                    finish(.failure(CancellationError()))
                    return
                }
                guard recorder.record(forDuration: Self.durationLimit) else {
                    finish(.failure(Failure.recordingFailed))
                    return
                }
                isRecording = true
                metering = Task { [weak self] in
                    while !Task.isCancelled {
                        guard let self else { return }
                        self.updateMeter()
                        do { try await Task.sleep(for: .milliseconds(100)) }
                        catch { return }
                    }
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in
                guard self?.recorder?.url == url else { return }
                self?.finish(.failure(CancellationError()))
            }
        }
        try Task.checkCancellation()
        keepFile = true
        return url
    }

    func stop() {
        guard let recorder, isRecording else { return }
        isRecording = false
        recorder.stop()
        finish(.success(()))
    }

    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        let url = recorder.url
        Task { @MainActor [weak self] in
            guard self?.recorder?.url == url else { return }
            self?.finish(flag ? .success(()) : .failure(Failure.recordingFailed))
        }
    }

    nonisolated func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: (any Error)?) {
        let url = recorder.url
        Task { @MainActor [weak self] in
            guard self?.recorder?.url == url else { return }
            self?.finish(.failure(Failure.recordingFailed))
        }
    }

    private func finish(_ result: Result<Void, any Error>) {
        let pending = completion
        completion = nil
        pending?.resume(with: result)
    }

    private func updateMeter() {
        guard let recorder, recorder.isRecording else { return }
        remainingSeconds = max(0, Int(ceil(Self.durationLimit - recorder.currentTime)))
        recorder.updateMeters()
        level = min(1, max(0, (Double(recorder.averagePower(forChannel: 0)) + 60) / 60))
    }
}
