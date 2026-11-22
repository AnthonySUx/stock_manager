import AVFoundation
import XCTest
@testable import StockManager

final class SpeechContractTests: XCTestCase {
    @MainActor func testRecordingSettingsProduceThreeSecondMonoPCM16WAV() throws {
        let settings = VoiceRecorder.settings
        XCTAssertEqual(settings[AVFormatIDKey] as? AudioFormatID, kAudioFormatLinearPCM)
        XCTAssertEqual(settings[AVSampleRateKey] as? Int, 16_000)
        XCTAssertEqual(settings[AVNumberOfChannelsKey] as? Int, 1)
        XCTAssertEqual(settings[AVLinearPCMBitDepthKey] as? Int, 16)
        XCTAssertEqual(settings[AVLinearPCMIsBigEndianKey] as? Bool, false)
        XCTAssertEqual(settings[AVLinearPCMIsFloatKey] as? Bool, false)
        XCTAssertLessThan(VoiceRecorder.durationLimit, 120)

        let url = try VoiceRecordingFixture.make()
        defer { try? FileManager.default.removeItem(at: url) }
        let wav = try Data(contentsOf: url)
        XCTAssertEqual(String(decoding: wav.prefix(4), as: UTF8.self), "RIFF")
        XCTAssertEqual(String(decoding: wav[8..<12], as: UTF8.self), "WAVE")
        let format = try XCTUnwrap(Self.chunk("fmt ", in: wav))
        XCTAssertGreaterThanOrEqual(format.count, 16)
        XCTAssertEqual(Self.littleEndian(format, offset: 0, length: 2), 1)
        XCTAssertEqual(Self.littleEndian(format, offset: 2, length: 2), 1)
        XCTAssertEqual(Self.littleEndian(format, offset: 4, length: 4), 16_000)
        XCTAssertEqual(Self.littleEndian(format, offset: 14, length: 2), 16)
        let samples = try XCTUnwrap(Self.chunk("data", in: wav))
        XCTAssertEqual(samples.count, 16_000 * 3 * 2)
    }

    @MainActor func testSpeechMultipartUsesFeatureWithoutLocaleAndDeletesSuccessfulRecording() async throws {
        let url = try VoiceRecordingFixture.make()
        defer { try? FileManager.default.removeItem(at: url) }
        let wav = try Data(contentsOf: url)
        let client = stubbedClient { request in
            XCTAssertEqual(request.url?.path, "/api/speech/transcribe")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.timeoutInterval, 60)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            let contentType = try XCTUnwrap(request.value(forHTTPHeaderField: "Content-Type"))
            let prefix = "multipart/form-data; boundary="
            XCTAssertTrue(contentType.hasPrefix(prefix))
            let boundary = String(contentType.dropFirst(prefix.count))
            var expected = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"feature\"\r\n\r\nstock_intake\r\n".utf8)
            expected.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"recording.wav\"\r\nContent-Type: audio/wav\r\n\r\n".utf8)
            expected.append(wav)
            expected.append(contentsOf: "\r\n--\(boundary)--\r\n".utf8)
            XCTAssertEqual(try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(APIContractTests.readBody)), expected)
            return (200, #"{"transcript":"Two bottles of milk","duration_ms":5230,"warnings":[{"code":"audio_stereo_left_only"}]}"#)
        }

        let result = try await VoiceInputStore.transcribeRecording(at: url, client: client, feature: .stockIntake)
        XCTAssertEqual(result.transcript, "Two bottles of milk")
        XCTAssertEqual(result.durationMs, 5230)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    @MainActor func testSpeechFailurePreservesAPIErrorAndDeletesRecording() async throws {
        let url = try VoiceRecordingFixture.make()
        defer { try? FileManager.default.removeItem(at: url) }
        let client = stubbedClient { request in
            let data = try XCTUnwrap(request.httpBody ?? request.httpBodyStream.map(APIContractTests.readBody))
            let form = String(decoding: data, as: UTF8.self)
            XCTAssertTrue(form.contains("name=\"feature\"\r\n\r\nrecipe_explore\r\n"))
            XCTAssertFalse(form.contains("name=\"locale\""))
            return (503, #"{"code":"asr_unavailable","detail":"Unavailable"}"#)
        }
        do {
            _ = try await VoiceInputStore.transcribeRecording(at: url, client: client, feature: .recipeExplore)
            XCTFail("Expected a transcription error")
        } catch {
            XCTAssertEqual(error.localizedDescription, DisplayText.error("asr_unavailable"))
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    @MainActor func testSpeechUnavailableRefreshesCapabilitiesAndHidesMicrophone() async throws {
        let url = try VoiceRecordingFixture.make()
        defer { try? FileManager.default.removeItem(at: url) }
        var capabilityRequests = 0
        let client = stubbedClient { request in
            if request.url?.path == "/api/capabilities" {
                capabilityRequests += 1
                let asr = capabilityRequests == 1
                return (200, #"{"ai":{"text":true,"vision":false,"asr":\#(asr)}}"#)
            }
            return (503, #"{"code":"asr_unavailable","detail":"Unavailable"}"#)
        }
        let capabilities = CapabilitiesStore()
        await capabilities.refresh(using: client)
        XCTAssertTrue(capabilities.value.ai.asr)

        let voice = VoiceInputStore()
        var transcripts: [String] = []
        await voice.transcribe(url, client: client, capabilities: capabilities, feature: .stockIntake) {
            transcripts.append($0)
        }

        XCTAssertEqual(voice.action.errorMessage, DisplayText.error("asr_unavailable"))
        XCTAssertFalse(capabilities.value.ai.asr)
        XCTAssertTrue(capabilities.value.ai.text)
        XCTAssertEqual(capabilityRequests, 2)
        XCTAssertTrue(transcripts.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    private func stubbedClient(_ handler: @escaping (URLRequest) throws -> (Int, String)) -> APIClient {
        URLProtocolStub.handler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return APIClient(baseURL: URL(string: "https://example.test/api")!, token: "test-token",
                         session: URLSession(configuration: configuration))
    }

    private static func chunk(_ name: String, in wav: Data) -> Data? {
        var offset = 12
        while offset + 8 <= wav.count {
            let tag = String(decoding: wav[offset..<(offset + 4)], as: UTF8.self)
            let length = littleEndian(wav, offset: offset + 4, length: 4)
            let start = offset + 8
            guard length <= wav.count - start else { return nil }
            if tag == name { return wav.subdata(in: start..<(start + length)) }
            offset = start + length + (length % 2)
        }
        return nil
    }

    private static func littleEndian(_ data: Data, offset: Int, length: Int) -> Int {
        (0..<length).reduce(0) { $0 | (Int(data[offset + $1]) << (8 * $1)) }
    }
}
