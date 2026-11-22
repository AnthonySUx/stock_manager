import SwiftUI

struct IntakeCandidateEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State private var candidate: IntakeCandidate
    @State private var quantity: String
    private let initialQuantity: String
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
            Section {
                Toggle("永久有效", isOn: Binding(
                    get: { candidate.unopenedExpirationDate == "infinite" },
                    set: { candidate.unopenedExpirationDate = $0 ? "infinite" : nil }
                ))
                if candidate.unopenedExpirationDate != "infinite" {
                    dateField("未开封到期日", key: "unopened_expiration_date", value: \.unopenedExpirationDate)
                }
                dateField("开封日期", key: "opened_date", value: \.openedDate)
                dateField("开封后到期日", key: "opened_expiration_date", value: \.openedExpirationDate)
            } header: {
                Text("有效期")
            } footer: {
                Text("日期格式为 YYYY-MM-DD。可留空，稍后补填。")
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
        marked(key) {
            HStack {
                Text(title)
                    .font(.subheadline)
                TextField("YYYY-MM-DD", text: text(value))
                    .accessibilityLabel(title)
                    .keyboardType(.numbersAndPunctuation)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("intake.editor.\(key)")
                if candidate[keyPath: value] != nil {
                    Button {
                        candidate[keyPath: value] = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("清空\(title)")
                    .accessibilityIdentifier("intake.clear.\(key)")
                }
            }
        }
    }

    private func marked<FieldContent: View>(_ key: String, @ViewBuilder content: () -> FieldContent) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            content()
            if issues.contains(key) || candidate.invalidDraftFields.contains(key) ||
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
