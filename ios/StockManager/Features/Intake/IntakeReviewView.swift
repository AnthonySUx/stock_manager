import PhotosUI
import SwiftUI
import UIKit

struct IntakeReviewView: View {
    private enum Operation { case parse, photos, confirm }

    private enum PhotoSelection {
        case library(PhotosPickerItem)
        case image(Data?)

        func prepare() async throws -> PreparedIntakeImage {
            let data: Data?
            switch self {
            case .library(let item):
                data = try await item.loadTransferable(type: Data.self)
            case .image(let image):
                data = image
            }
            guard let data else { throw ImagePreparation.Failure.unreadable }
            return try await Task.detached(priority: .userInitiated) {
                try ImagePreparation.prepare(data)
            }.value
        }
    }

    @Environment(\.dismiss) private var dismiss
    @Environment(InventoryStore.self) private var inventory
    @Environment(CategoryStore.self) private var categories
    @Environment(CapabilitiesStore.self) private var capabilities
    @Bindable var store: IntakeStore
    @State private var text = ""
    @State private var voice = VoiceInputStore()
    @State private var showsPhotoPicker = false
    @State private var showsCamera = false
    @State private var selectedPhotos: [PhotosPickerItem] = []
    @State private var photoPreparationErrors: [String] = []
    @State private var editedCandidate: IntakeCandidate?
    @State private var operation: Operation?
    @State private var confirmationMessage: String?
    @State private var restockNames: [Int: String] = [:]
    @FocusState private var inputFocused: Bool

    var body: some View {
        ScrollViewReader { scroll in
            Form {
                inputSection
                photoSection
                feedbackSection
                if let review = store.lastParse {
                    reviewNotes(review, scroll: scroll)
                }
                draftSection
                defaultsSection
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: store.serverIssue) { _, issue in
                if let issue { scroll.scrollTo(issue.temporaryId, anchor: .center) }
            }
        }
        .navigationTitle("AI 入库")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("关闭") { dismiss() }.disabled(isBusy)
            }
        }
        .interactiveDismissDisabled(isBusy)
        .onDisappear { voice.cancel() }
        .safeAreaInset(edge: .bottom, spacing: 0) { confirmationBar }
        .sheet(item: $editedCandidate) { candidate in
            NavigationStack {
                IntakeCandidateEditor(candidate: candidate, categories: categories.flat,
                                      issues: issues(for: candidate.id), onSave: store.replaceCandidate)
            }
        }
        .photosPicker(isPresented: $showsPhotoPicker, selection: $selectedPhotos,
                      selectionBehavior: .ordered, matching: .images, preferredItemEncoding: .current)
        .onChange(of: selectedPhotos) { _, result in
            guard !result.isEmpty else { return }
            selectedPhotos = []
            upload(result.map(PhotoSelection.library))
        }
        .fullScreenCover(isPresented: $showsCamera) {
            IntakeCamera { data in
                showsCamera = false
                upload([.image(data)])
            } onCancel: {
                showsCamera = false
            }
            .ignoresSafeArea()
        }
        .task {
            if categories.flat.isEmpty { await categories.load() }
        }
        .task {
            if let pending = try? await inventory.client.restockItems(status: "pending") {
                restockNames = Dictionary(pending.map { ($0.id, $0.name) }, uniquingKeysWith: { first, _ in first })
            }
        }
    }

    private var isBusy: Bool { operation != nil || store.action.isRunning || voice.action.isRunning }

    private var inputSection: some View {
        Section {
            TextField("例如：两斤五花肉，一盒鸡蛋", text: $text, axis: .vertical)
                .lineLimit(3...6)
                .focused($inputFocused)
                .accessibilityIdentifier("intake.input")
                .disabled(isBusy)
            VoiceInputControl(voice: voice, isAvailable: capabilities.value.ai.asr, isDisabled: isBusy) {
                inputFocused = false
                voice.start(client: inventory.client, feature: .stockIntake) { text.appendVoiceTranscript($0) }
            }
            Button("解析文字", systemImage: "sparkles") { parse() }
                .disabled(isBusy || store.photoUpload != nil || text.nilIfBlank == nil || !capabilities.value.ai.text)
                .accessibilityIdentifier("intake.parse")
        } header: {
            Text("物品描述")
        } footer: {
            if !capabilities.value.ai.text { Text(DisplayText.aiUnavailable) }
        }
    }

    @ViewBuilder private var photoSection: some View {
        if capabilities.value.ai.vision || store.photoUpload != nil || !photoPreparationErrors.isEmpty {
            Section("照片与小票") {
                if capabilities.value.ai.vision, store.photoUpload == nil {
                    Button("从相册选择", systemImage: "photo.on.rectangle") {
                        inputFocused = false
                        openPhotoLibrary()
                    }
                    .disabled(isBusy)
                    .accessibilityIdentifier("intake.photos")
                    if UIImagePickerController.isSourceTypeAvailable(.camera) {
                        Button("拍照", systemImage: "camera") {
                            inputFocused = false
                            showsCamera = true
                        }
                        .disabled(isBusy)
                    }
                }
                if let upload = store.photoUpload, !isBusy {
                    Text("已暂停 · 第 \(upload.batch)/\(upload.totalBatches) 批")
                    Button("重试本批", systemImage: "arrow.clockwise") { retryUpload() }
                        .disabled(!capabilities.value.ai.vision)
                    Button("放弃剩余照片", role: .destructive) { store.discardPhotoUpload() }
                }
                ForEach(Array(photoPreparationErrors.enumerated()), id: \.offset) { _, message in
                    Text(message).foregroundStyle(.red)
                }
            }
        }
    }

    @ViewBuilder private var feedbackSection: some View {
        if let operation {
            Section {
                switch operation {
                case .confirm: ProgressView("正在确认入库…")
                case .parse: ProgressView("正在解析文字…")
                case .photos:
                    if let upload = store.photoUpload {
                        ProgressView("正在解析照片 · 第 \(upload.batch)/\(upload.totalBatches) 批")
                    } else {
                        ProgressView("正在准备照片…")
                    }
                }
            }
        } else if let message = store.action.errorMessage {
            Section {
                Label(message, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
            }
        } else if let confirmationMessage {
            Section {
                Label(confirmationMessage, systemImage: "checkmark.circle")
            }
        }
    }

    @ViewBuilder private func reviewNotes(_ review: IntakeParseReview, scroll: ScrollViewProxy) -> some View {
        if !review.clarifications.isEmpty {
            Section("待澄清") {
                ForEach(Array(review.clarifications.enumerated()), id: \.offset) { _, clarification in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(clarification.question)
                        ForEach(clarification.temporaryIds, id: \.self) { id in
                            if let candidate = store.candidates.first(where: { $0.id == id }) {
                                Button(candidateTitle(candidate), systemImage: "arrow.down.circle") {
                                    inputFocused = false
                                    scroll.scrollTo(id, anchor: .center)
                                    editedCandidate = candidate
                                }
                                .buttonStyle(.borderless)
                                .disabled(isBusy)
                            }
                        }
                    }
                }
            }
        }
        if !review.warnings.isEmpty || !review.unparsedFragments.isEmpty {
            Section("解析提示") {
                ForEach(Array(review.warnings.enumerated()), id: \.offset) { _, warning in
                    Text(DisplayText.intakeWarning(warning))
                }
                if !review.unparsedFragments.isEmpty {
                    LabeledContent("未识别内容", value: review.unparsedFragments.joined(separator: "、"))
                }
            }
        }
    }

    private var draftSection: some View {
        let issues = Dictionary(grouping: store.confirmationIssues, by: \.temporaryId)
        return Section("入库草稿") {
            ForEach(store.candidates) { candidate in
                let fields = issueFields(issues[candidate.id] ?? [], candidateID: candidate.id)
                candidateRow(candidate, fields: fields).id(candidate.id)
            }
            Button("手动添加", systemImage: "plus") {
                inputFocused = false
                editedCandidate = store.addManualCandidate()
                confirmationMessage = nil
            }
            .disabled(store.candidates.count >= IntakeStore.maxCandidates)
        }
        .disabled(isBusy)
    }

    private func candidateRow(_ candidate: IntakeCandidate, fields: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                inputFocused = false
                editedCandidate = candidate
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(candidateTitle(candidate)).font(.headline).foregroundStyle(.primary)
                        Text(candidateDetails(candidate)).font(.subheadline).foregroundStyle(.secondary)
                        Text("到期日：\(expirationLabel(candidate.unopenedExpirationDate))")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("intake.candidate.\(candidate.id)")

            if let source = DisplayText.intakeSource(candidate.source) {
                Label(source, systemImage: "photo").foregroundStyle(.secondary)
            }
            if candidate.source.inputKind == "receipt" {
                if let raw = candidate.rawName?.nilIfBlank, raw != candidateTitle(candidate) {
                    Text("小票原文：\(raw)").foregroundStyle(.secondary)
                }
                if let generic = candidate.genericName?.nilIfBlank {
                    Text("商品类型：\(generic)").foregroundStyle(.secondary)
                }
            }
            if candidate.confidence < 0.6 || candidate.fieldConfidence.values.contains(where: { $0 < 0.6 }) {
                Label("置信度较低，请核对", systemImage: "exclamationmark.circle").foregroundStyle(.orange)
            }
            ForEach(Array(candidate.warnings.enumerated()), id: \.offset) { _, warning in
                Text(DisplayText.intakeWarning(warning)).foregroundStyle(.secondary)
            }
            if candidate.unopenedExpirationDate == nil, let date = candidate.suggestedUnopenedExpirationDate {
                HStack {
                    let fromCategory = candidate.warnings.contains {
                        $0.code == "expiration_date_inferred" && $0.params["basis"] == "category_default"
                    }
                    Text(fromCategory ? "建议 \(date)（按分类默认保质期）" : "建议 \(date)")
                    Spacer()
                    Button("采用") { adopt(candidate) }.buttonStyle(.borderless)
                        .accessibilityIdentifier("intake.adopt.\(candidate.id)")
                }
            }
            if let id = candidate.matchedRestockId {
                HStack {
                    Text(restockLabel(candidate.restockAction, name: restockNames[id] ?? "补货条目 #\(id)"))
                    Spacer()
                    Button("取消关联") { unlink(candidate) }.buttonStyle(.borderless)
                }
            }
            if !fields.isEmpty {
                Label("请检查：\(fields.map(DisplayText.intakeField).joined(separator: "、"))",
                      systemImage: "exclamationmark.circle")
                    .foregroundStyle(.red)
                    .accessibilityIdentifier("intake.issues.\(candidate.id)")
            }
        }
        .font(.caption)
        .padding(.vertical, 4)
        .swipeActions {
            Button("移除", role: .destructive) { store.removeCandidate(id: candidate.id) }
        }
    }

    private var defaultsSection: some View {
        Section("批量设置") {
            InventoryTextField(.owner, text: Binding(
                get: { store.defaults.owner ?? "" }, set: { store.defaults.owner = $0.isEmpty ? nil : $0 }
            )).accessibilityIdentifier("intake.defaultOwner")
            InventoryTextField(.location, text: Binding(
                get: { store.defaults.location ?? "" }, set: { store.defaults.location = $0.isEmpty ? nil : $0 }
            )).accessibilityIdentifier("intake.defaultLocation")
        }
        .disabled(isBusy)
    }

    private var confirmationBar: some View {
        Button {
            confirm()
        } label: {
            Text("确认入库（\(store.candidates.count)）").frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(!store.canConfirm || isBusy)
        .accessibilityIdentifier("intake.confirm")
        .padding()
        .background(.bar)
    }

    private func candidateTitle(_ candidate: IntakeCandidate) -> String {
        candidate.name?.nilIfBlank ?? candidate.rawName?.nilIfBlank ?? "未命名条目"
    }

    private func candidateDetails(_ candidate: IntakeCandidate) -> String {
        let category = categories.flat.first { $0.id == candidate.categoryId }?.name ?? "未选分类"
        let quantity = [candidate.quantityValue?.formatted(), candidate.quantityUnit?.nilIfBlank]
            .compactMap { $0 }.joined(separator: " ")
        return "\(category) · \(quantity.isEmpty ? "数量未填写" : quantity)"
    }

    private func expirationLabel(_ date: String?) -> String {
        if date == "infinite" { return "永久有效" }
        return date?.nilIfBlank ?? "未填写"
    }

    private func restockLabel(_ action: String?, name: String) -> String {
        switch action {
        case "done": "将完成补货：\(name)"
        case "partial": "部分补货：\(name)"
        default: "关联补货：\(name)"
        }
    }

    private func issues(for id: String) -> [String] {
        issueFields(store.confirmationIssues.filter { $0.temporaryId == id }, candidateID: id)
    }

    private func issueFields(_ issues: [IntakeFieldIssue], candidateID: String) -> [String] {
        var fields = issues.map(\.field)
        if let issue = store.serverIssue, issue.temporaryId == candidateID, !fields.contains(issue.field) {
            fields.insert(issue.field, at: 0)
        }
        return fields
    }

    private func adopt(_ candidate: IntakeCandidate) {
        var updated = candidate
        updated.adoptSuggestedExpiration()
        store.replaceCandidate(updated)
    }

    private func unlink(_ candidate: IntakeCandidate) {
        var updated = candidate
        updated.removeRestockLink()
        store.replaceCandidate(updated)
    }

    private func parse() {
        guard !isBusy, store.photoUpload == nil, capabilities.value.ai.text, let input = text.nilIfBlank else { return }
        inputFocused = false
        confirmationMessage = nil
        operation = .parse
        Task {
            defer { operation = nil }
            if await store.parse(text: input) { text = "" }
        }
    }

    private func openPhotoLibrary() {
        #if DEBUG
        if let fixtures = IntakeUITestHost.photoFixtures {
            upload(fixtures.map { .image($0) })
            return
        }
        #endif
        showsPhotoPicker = true
    }

    private func upload(_ selections: [PhotoSelection]) {
        guard !isBusy, capabilities.value.ai.vision, store.photoUpload == nil else { return }
        operation = .photos
        confirmationMessage = nil
        photoPreparationErrors = []
        Task {
            defer { operation = nil }
            var images: [PreparedIntakeImage] = []
            for (index, selection) in selections.enumerated() {
                do {
                    images.append(try await selection.prepare())
                } catch ImagePreparation.Failure.tooLarge {
                    photoPreparationErrors.append("第 \(index + 1) 张图片超过大小限制")
                } catch {
                    photoPreparationErrors.append("无法读取第 \(index + 1) 张图片")
                }
            }
            guard capabilities.value.ai.vision else {
                photoPreparationErrors.append(DisplayText.aiUnavailable)
                return
            }
            await store.parse(photos: images)
        }
    }

    private func retryUpload() {
        guard !isBusy, capabilities.value.ai.vision else { return }
        operation = .photos
        Task {
            defer { operation = nil }
            await store.retryPhotoUpload()
        }
    }

    private func confirm() {
        guard !isBusy, store.canConfirm else { return }
        inputFocused = false
        confirmationMessage = nil
        operation = .confirm
        Task {
            defer { operation = nil }
            if let result = await store.confirm() {
                if case .succeeded(let message) = store.action, let message {
                    confirmationMessage = message
                } else {
                    confirmationMessage = "已入库 \(result.created.count) 项"
                }
            }
        }
    }
}
