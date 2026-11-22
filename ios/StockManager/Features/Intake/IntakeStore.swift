import Foundation
import Observation

struct IntakeFieldIssue: Hashable {
    let temporaryId: String
    let field: String
}

struct IntakeParseReview {
    let clarifications: [IntakeClarification]
    let unparsedFragments: [String]
    let locale: String
    let warnings: [AIWarning]
}

@MainActor @Observable
final class IntakeStore {
    static let maxTextLength = 4_000
    static let maxCandidates = 100
    private static let photoBatchSize = 8

    struct PhotoUpload {
        fileprivate var remaining: [PreparedIntakeImage]
        fileprivate let draftPurchaseDate: String?
        let totalBatches: Int
        fileprivate(set) var batch = 1
    }

    private(set) var photoUpload: PhotoUpload?

    private let client: any APIClientProtocol
    private let inventory: InventoryStore
    private let restock: RestockStore
    private(set) var candidates: [IntakeCandidate]
    private(set) var lastParse: IntakeParseReview?
    private(set) var action: ActionState = .idle
    private(set) var serverIssue: IntakeFieldIssue?
    var defaults = IntakeConfirmDefaults() {
        didSet {
            if defaults != oldValue { clearFailure() }
        }
    }
    var purchaseDate: String?

    init(client: any APIClientProtocol, inventory: InventoryStore, restock: RestockStore,
         candidates: [IntakeCandidate] = []) {
        self.client = client
        self.inventory = inventory
        self.restock = restock
        self.candidates = candidates
    }

    var canConfirm: Bool {
        !action.isRunning && photoUpload == nil && (1...Self.maxCandidates).contains(candidates.count) && confirmationIssues.isEmpty
    }

    var draftIssues: [IntakeFieldIssue] {
        candidates.flatMap { candidate in
            candidate.invalidDraftFields.map { IntakeFieldIssue(temporaryId: candidate.id, field: $0) }
        }
    }

    var confirmationIssues: [IntakeFieldIssue] {
        let defaults = defaults.normalized
        let missing = candidates.flatMap { candidate in
            let item = IntakeConfirmItem(candidate: candidate)
            var fields: [String] = []
            if item.name == nil { fields.append("name") }
            if item.categoryId == nil { fields.append("category_id") }
            if item.quantityValue == nil { fields.append("quantity_value") }
            if item.quantityUnit == nil { fields.append("quantity_unit") }
            if item.unopenedExpirationDate == nil { fields.append("unopened_expiration_date") }
            if item.owner == nil && defaults.owner == nil { fields.append("owner") }
            if item.location == nil && defaults.location == nil { fields.append("location") }
            return fields.map { IntakeFieldIssue(temporaryId: candidate.temporaryId, field: $0) }
        }
        let invalid = draftIssues
        let invalidSet = Set(invalid)
        return invalid + missing.filter { !invalidSet.contains($0) }
    }

    @discardableResult
    func addManualCandidate() -> IntakeCandidate? {
        guard !action.isRunning, candidates.count < Self.maxCandidates else { return nil }
        let taken = Set(candidates.map(\.temporaryId))
        var id: String
        repeat {
            id = "cand_" + UUID().uuidString.prefix(8).lowercased()
        } while taken.contains(id)
        let candidate = IntakeCandidate.manual(temporaryId: id)
        candidates.append(candidate)
        clearFailure()
        return candidate
    }

    func replaceCandidate(_ candidate: IntakeCandidate) {
        guard !action.isRunning, let index = candidates.firstIndex(where: { $0.id == candidate.id }) else { return }
        candidates[index] = candidate
        if serverIssue?.temporaryId == candidate.id { serverIssue = nil }
        clearFailure()
    }

    func removeCandidate(id: String) {
        guard !action.isRunning else { return }
        let previousCount = candidates.count
        candidates.removeAll { $0.id == id }
        if serverIssue?.temporaryId == id { serverIssue = nil }
        if candidates.count != previousCount { clearFailure() }
    }

    private func clearFailure() {
        if case .failed = action { action = .idle }
    }

    @discardableResult
    func parse(text: String, locale: String? = nil, timezone: String? = nil) async -> Bool {
        guard !action.isRunning, photoUpload == nil, !Task.isCancelled else { return false }
        serverIssue = nil
        let text = text.trimmed
        guard !text.isEmpty else {
            action = .failed(DisplayText.error("intake_text_empty") ?? "")
            return false
        }
        guard text.unicodeScalars.count <= Self.maxTextLength else {
            action = .failed(DisplayText.error("intake_text_too_long", params: ["max": .integer(Self.maxTextLength)]) ?? "")
            return false
        }
        guard validateDraftForParsing() else { return false }

        let request = IntakeParseRequest(input: .init(text: text), draft: .init(items: candidates),
                                         context: .init(locale: locale, timezone: timezone, purchaseDate: contextPurchaseDate))
        action = .running
        do {
            let response = try await client.parseIntake(request)
            try Task.checkCancellation()
            try apply(response)
            action = .succeeded(nil)
            return true
        } catch {
            if Task.isCancelled { action = .idle }
            else { record(error, candidateIDs: request.draft.items.map(\.temporaryId)) }
            return false
        }
    }

    func parse(photos: [PreparedIntakeImage]) async {
        guard !action.isRunning, photoUpload == nil, !photos.isEmpty, !Task.isCancelled else { return }
        let batches = (photos.count - 1) / Self.photoBatchSize + 1
        photoUpload = .init(remaining: photos, draftPurchaseDate: contextPurchaseDate, totalBatches: batches)
        await retryPhotoUpload()
    }

    func retryPhotoUpload() async {
        guard !action.isRunning, photoUpload != nil, !Task.isCancelled else { return }
        serverIssue = nil
        action = .running
        while let upload = photoUpload {
            guard validateDraftForParsing() else { return }
            let batch = Array(upload.remaining.prefix(Self.photoBatchSize))
            // A context date applies to the entire request. Use a photo date only when every photo agrees.
            let commonDate = batch.first?.captureDate.flatMap { date in
                batch.allSatisfy { $0.captureDate == date } ? date : nil
            }
            let context = IntakeContext(purchaseDate: purchaseDate?.nilIfBlank ?? commonDate ?? upload.draftPurchaseDate)
            do {
                let response = try await client.parseIntakeImages(batch, draft: .init(items: candidates), context: context)
                try Task.checkCancellation()
                try apply(response, appendingReview: upload.batch > 1)
                if batch.count == upload.remaining.count {
                    photoUpload = nil
                } else {
                    photoUpload?.remaining.removeFirst(batch.count)
                    photoUpload?.batch += 1
                }
            } catch {
                record(error, candidateIDs: candidates.map(\.temporaryId))
                return
            }
        }
        action = .succeeded(nil)
    }

    func discardPhotoUpload() {
        guard !action.isRunning else { return }
        photoUpload = nil
        clearFailure()
    }

    private func validateDraftForParsing() -> Bool {
        guard candidates.count <= Self.maxCandidates else {
            action = .failed(Self.draftLimitMessage)
            return false
        }
        if let issue = draftIssues.first {
            serverIssue = issue
            action = .failed("草稿中的\(DisplayText.intakeField(issue.field))无效，请修改后再解析")
            return false
        }
        return true
    }

    private func apply(_ response: IntakeParseResponse, appendingReview: Bool = false) throws {
        let (updated, clarification) = try applying(response.operations)
        let previous = appendingReview ? lastParse : nil
        candidates = updated
        lastParse = .init(clarifications: (previous?.clarifications ?? []) + clarification,
                          unparsedFragments: (previous?.unparsedFragments ?? []) + response.unparsedFragments,
                          locale: response.locale, warnings: (previous?.warnings ?? []) + response.warnings)
    }

    @discardableResult
    func confirm() async -> IntakeConfirmResponse? {
        guard !action.isRunning, !Task.isCancelled else { return nil }
        serverIssue = nil
        guard canConfirm else {
            action = .failed(candidates.count > Self.maxCandidates ? Self.draftLimitMessage : "请补齐待入库条目的信息")
            return nil
        }
        let request = IntakeConfirmRequest(defaults: defaults.normalized,
                                           items: candidates.map(IntakeConfirmItem.init(candidate:)))
        action = .running
        // Once submitted, finish the write and reconcile it even if the view's task is cancelled.
        // Otherwise the draft could still contain items the server has already saved.
        return await Task { await finishConfirmation(request) }.value
    }

    private func finishConfirmation(_ request: IntakeConfirmRequest) async -> IntakeConfirmResponse? {
        do {
            let response = try await client.confirmIntake(request)
            // Reconcile a successful write before refreshing the other stores.
            let created = Set(response.created.map(\.temporaryId))
            candidates.removeAll { created.contains($0.temporaryId) }
            if candidates.isEmpty { lastParse = nil }
            async let refreshInventory: Void = inventory.load()
            async let refreshRestock: Void = restock.load()
            _ = await (refreshInventory, refreshRestock)
            let warning = response.warnings.first { $0.code == "restock_already_done" }
            action = .succeeded(warning.map(DisplayText.intakeWarning))
            return response
        } catch {
            record(error, candidateIDs: request.items.map(\.temporaryId))
            return nil
        }
    }

    private var contextPurchaseDate: String? {
        if let date = purchaseDate?.nilIfBlank { return date }
        // A date shared across the draft can supply context without choosing between conflicting dates.
        let dates = Set(candidates.compactMap { $0.purchaseDate?.nilIfBlank })
        return dates.count == 1 ? dates.first : nil
    }

    private func applying(_ operations: [IntakeOperation]) throws -> ([IntakeCandidate], [IntakeClarification]) {
        var updated = candidates
        var clarification: [IntakeClarification] = []
        for operation in operations {
            switch operation {
            case .add(let candidate, _):
                guard !updated.contains(where: { $0.id == candidate.id }) else { throw ApplyError.invalidTarget }
                updated.append(candidate)
            case .update(let id, let changes, _):
                guard let index = updated.firstIndex(where: { $0.id == id }) else { throw ApplyError.invalidTarget }
                updated[index] = try updated[index].applying(changes)
            case .delete(let id, _, _):
                guard let index = updated.firstIndex(where: { $0.id == id }) else { throw ApplyError.invalidTarget }
                updated.remove(at: index)
            case .clarify(let question):
                clarification.append(question)
            case .unknown:
                continue
            }
        }
        guard updated.count <= Self.maxCandidates else { throw ApplyError.draftLimit(Self.maxCandidates) }
        return (updated, clarification)
    }

    private func record(_ error: Error, candidateIDs: [String]) {
        if error is CancellationError || (error as? URLError)?.code == .cancelled {
            action = .idle
            return
        }
        if case .server(_, "intake_item_invalid", let params, _) = error as? APIClientError,
           let field = params["field"]?.text {
            let id = params["temporary_id"]?.text
            let index = params["index"]?.text.flatMap(Int.init)
            let indexedID = index.flatMap { candidateIDs.indices.contains($0) ? candidateIDs[$0] : nil }
            if let target = id.flatMap({ candidateIDs.contains($0) ? $0 : nil }) ?? indexedID {
                serverIssue = .init(temporaryId: target, field: field)
            }
        }
        action = .failed(error.localizedDescription)
    }

    private static var draftLimitMessage: String {
        DisplayText.error("intake_draft_too_large", params: ["max": .integer(maxCandidates)]) ?? ""
    }

    private enum ApplyError: LocalizedError {
        case invalidTarget
        case draftLimit(Int)

        var errorDescription: String? {
            switch self {
            case .invalidTarget: "无法将解析结果应用到当前草稿，请重试"
            case .draftLimit(let limit): DisplayText.error("intake_draft_too_large", params: ["max": .integer(limit)])
            }
        }
    }
}
