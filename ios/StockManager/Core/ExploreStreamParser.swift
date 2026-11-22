import Foundation

struct ExploreStreamCompletion: Decodable, Hashable {
    let mode: String
    let inputMode: String
    let locale: String
    let warnings: [AIWarning]
    let count: Int
}

enum ExploreStreamEvent: Equatable {
    case idea(ExploreIdea)
    case done(ExploreStreamCompletion)
    case error(code: String)

    var isTerminal: Bool {
        switch self {
        case .idea: false
        case .done, .error: true
        }
    }
}

struct ExploreStreamParser {
    private struct Failure: Decodable { let code: String }

    private var line: [UInt8] = []
    private var skipLineFeed = false
    private var eventName = ""
    private var dataLines: [String] = []
    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    mutating func receive(_ byte: UInt8) throws -> ExploreStreamEvent? {
        // Foundation's .lines omits empty lines, which are the SSE event delimiters.
        let followsCarriageReturn = skipLineFeed
        skipLineFeed = byte == 0x0D
        if byte == 0x0A && followsCarriageReturn { return nil }
        guard byte == 0x0A || byte == 0x0D else {
            line.append(byte)
            return nil
        }
        return try readLine()
    }

    mutating func finish() throws -> ExploreStreamEvent? {
        if !line.isEmpty, let event = try readLine() { return event }
        return try dispatch()
    }

    private mutating func readLine() throws -> ExploreStreamEvent? {
        if line.isEmpty { return try dispatch() }
        let text = String(decoding: line, as: UTF8.self)
        line.removeAll(keepingCapacity: true)
        if text.hasPrefix(":") { return nil }

        let parts = text.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        var value = parts.count == 2 ? parts[1] : ""
        if value.first == " " { value.removeFirst() }
        switch parts[0] {
        case "event": eventName = String(value)
        case "data": dataLines.append(String(value))
        default: break
        }
        return nil
    }

    private mutating func dispatch() throws -> ExploreStreamEvent? {
        defer {
            eventName = ""
            dataLines.removeAll(keepingCapacity: true)
        }
        guard !dataLines.isEmpty else { return nil }
        let data = Data(dataLines.joined(separator: "\n").utf8)
        do {
            switch eventName {
            case "idea": return .idea(try decoder.decode(ExploreIdea.self, from: data))
            case "done": return .done(try decoder.decode(ExploreStreamCompletion.self, from: data))
            case "error": return .error(code: try decoder.decode(Failure.self, from: data).code)
            default: return nil
            }
        } catch {
            throw APIClientError.decoding(error.localizedDescription)
        }
    }
}
