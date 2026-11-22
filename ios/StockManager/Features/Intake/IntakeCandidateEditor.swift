import SwiftUI

struct IntakeCandidateEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State private var candidate: IntakeCandidate
    @State private var quantity: String
    private let initialQuantity: String
    private let initialCandidate: IntakeCandidate
    let categories: [Category]
    let issues: [String]
    let onSave: (IntakeCandidate) -> Void

    init(candidate: IntakeCandidate, categories: [Category], issues: [String],
         onSave: @escaping (IntakeCandidate) -> Void) {
        let quantity = candidate.quantityValue.map {
            $0.formatted(.number.grouping(.never).precision(.fractionLength(0...15)))
        } ?? ""
        _candidate = State(initialValue: candidate)
        _quantity = State(initialValue: quantity)
        initialQuantity = quantity
        initialCandidate = candidate
        self.categories = categories
        self.issues = issues
        self.onSave = onSave
    }

    var body: some View {
        Form {
            Section("基本信息") {
                marked("name") { InventoryTextField(.name, text: text(\.name)) }
                marked("category_id") {
                    InventoryCategoryPicker(categories: categories, selection: $candidate.categoryId)
                }
                marked("owner") { InventoryTextField(.owner, text: text(\.owner)) }
                marked("location") { InventoryTextField(.location, text: text(\.location)) }
                dateField("购买日期", key: "purchase_date", value: \.purchaseDate)
            }
            Section("数量") {
                marked("quantity_value") {
                    InventoryTextField(.quantity, text: $quantity)
                        .accessibilityIdentifier("intake.editor.quantity_value")
                }
                marked("quantity_unit") { InventoryTextField(.unit, text: text(\.quantityUnit)) }
            }
            Section("有效期") {
                Toggle("永久有效", isOn: Binding(
                    get: { candidate.unopenedExpirationDate == "infinite" },
                    set: { candidate.unopenedExpirationDate = $0 ? "infinite" : nil }
                ))
                if candidate.unopenedExpirationDate != "infinite" {
                    dateField("未开封到期日", key: "unopened_expiration_date", value: \.unopenedExpirationDate)
                }
                dateField("开封日期", key: "opened_date", value: \.openedDate)
                dateField("开封后到期日", key: "opened_expiration_date", value: \.openedExpirationDate)
            }
            Section("备注") {
                TextField("备注", text: text(\.notes), axis: .vertical)
            }
        }
        .navigationTitle("编辑入库条目")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("保存草稿") { save() }
                    .disabled(quantityIsInvalid)
            }
        }
    }

    private var quantityIsInvalid: Bool {
        guard quantity != initialQuantity, let entered = quantity.nilIfBlank else { return false }
        guard let parsed = entered.quantityValue() else { return true }
        return !parsed.isFinite || parsed <= 0
    }

    private func text(_ keyPath: WritableKeyPath<IntakeCandidate, String?>) -> Binding<String> {
        Binding(
            get: { candidate[keyPath: keyPath] ?? "" },
            set: { candidate[keyPath: keyPath] = $0.isEmpty ? nil : $0 }
        )
    }

    private func dateField(_ title: String, key: String,
                           value: WritableKeyPath<IntakeCandidate, String?>) -> some View {
        let raw = candidate[keyPath: value]
        let hasIssue = (key == "unopened_expiration_date" && raw == nil) ||
            (raw == initialCandidate[keyPath: value] && issues.contains(key))
        return marked(key, hasIssue: hasIssue) {
            HStack {
                if let raw {
                    if let date = API.date(raw), API.string(date) == raw {
                        DatePicker(title, selection: Binding(
                            get: { API.date(candidate[keyPath: value]) ?? date },
                            set: { candidate[keyPath: value] = API.string($0) }
                        ), displayedComponents: .date)
                        .accessibilityIdentifier("intake.editor.\(key)")
                    } else {
                        LabeledContent {
                            Text(verbatim: raw.isEmpty ? "空字符串" : raw)
                                .foregroundStyle(.red)
                                .accessibilityIdentifier("intake.invalid.\(key)")
                        } label: {
                            Text(title)
                        }
                    }
                    Button {
                        candidate[keyPath: value] = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("清空\(title)")
                    .accessibilityIdentifier("intake.clear.\(key)")
                } else {
                    LabeledContent(title, value: "未填写")
                    Button("设置") {
                        candidate[keyPath: value] = API.string(Calendar.current.startOfDay(for: .now))
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("设置\(title)")
                    .accessibilityIdentifier("intake.set.\(key)")
                }
            }
        }
    }

    private func marked<FieldContent: View>(_ key: String, hasIssue: Bool? = nil,
                                             @ViewBuilder content: () -> FieldContent) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            content()
            if (hasIssue ?? issues.contains(key)) || candidate.invalidDraftFields.contains(key) ||
                (key == "quantity_value" && quantityIsInvalid) {
                Label("请检查\(DisplayText.intakeField(key))", systemImage: "exclamationmark.circle")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .accessibilityIdentifier("intake.editor.issue.\(key)")
            }
        }
    }

    private func save() {
        guard !quantityIsInvalid else { return }
        if quantity != initialQuantity { candidate.quantityValue = quantity.nilIfBlank?.quantityValue() }
        onSave(candidate)
        dismiss()
    }
}
