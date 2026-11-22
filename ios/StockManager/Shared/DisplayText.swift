enum DisplayText {
    static let restockAlreadyDone = "这条补货之前已经入库，无需重复操作"
    static let aiUnavailable = "AI 功能未开启"
    static let recipeDifficulties = ["easy", "medium", "hard"]
    static let aiOutputLocales = ["zh-CN", "en", "ja"]

    static func aiOutputLocale(_ code: String?) -> String {
        switch code {
        case nil: "跟随设备"
        case "zh-CN": "简体中文"
        case "en": "English"
        case "ja": "日本語"
        case let code?: code
        }
    }

    static func error(_ code: String, params: [String: JSONValue] = [:]) -> String? {
        let max = params["max"]?.text
        switch code {
        case "ai_unavailable": return aiUnavailable
        case "ai_upstream_error": return "AI 服务暂时不可用，请重试"
        case "internal_error": return "服务器内部错误，请重试"
        case "ai_vision_unavailable": return "AI 图片识别功能未开启"
        case "intake_request_too_large": return "上传内容超过大小限制，请减少文件数量或大小"
        case "intake_text_empty": return "请输入入库内容"
        case "intake_text_too_long": return max.map { "入库文字不能超过 \($0) 字" } ?? "入库文字过长"
        case "intake_draft_too_large": return max.map { "入库草稿不能超过 \($0) 条" } ?? "入库草稿条目过多"
        case "intake_duplicate_temporary_id": return "入库草稿包含重复条目"
        case "intake_timezone_invalid": return "入库时区无效"
        case "intake_images_missing": return "请选择要上传的图片"
        case "intake_multipart_invalid": return "图片上传表单无效"
        case "intake_images_too_many": return max.map { "一次最多上传 \($0) 张图片" } ?? "一次上传的图片过多"
        case "intake_image_too_large": return "\(indexedLabel("图片", counter: "张", index: params["index"]))超过大小限制"
        case "intake_image_type_unsupported": return "\(indexedLabel("图片", counter: "张", index: params["index"]))的格式不受支持"
        case "intake_item_invalid": return "\(indexedLabel("条目", counter: "个", index: params["index"]))的入库信息无效，请检查后重试"
        case "asr_unavailable": return "语音转写功能未开启"
        case "audio_upload_invalid": return "语音上传表单无效或缺少录音文件"
        case "audio_too_large": return "录音文件超过大小限制"
        case "audio_format_unsupported": return "录音格式无效或不受支持"
        case "audio_too_long": return "录音不能超过 120 秒"
        case "asr_upstream_error": return "语音转写服务暂时不可用，请重试"
        default: return nil
        }
    }

    static func aiWarning(_ warning: AIWarning) -> String {
        let params = warning.params
        switch warning.code {
        case "locale_fallback":
            return params["requested"].map { "不支持请求的语言（\($0)），已改用可用语言" } ?? "已改用可用语言"
        case "draft_ai_generated":
            return "此草稿由 AI 生成，请检查食材、用量和步骤后再保存。"
        case "idea_dropped_malformed":
            return "已省略一条格式不完整的创意"
        case "idea_dropped_wrong_language":
            return params["title"].map { "创意「\($0)」的语言不符，已省略" } ?? "已省略一条语言不符的创意"
        case "field_value_dropped":
            let field = params["field"].map(aiField) ?? "字段"
            return params["value"].map { "\(field)的值「\($0)」无效，已清除" } ?? "\(field)的无效内容已清除"
        case "quantity_dropped":
            return params["ingredient"].map { "「\($0)」的用量或单位无效，已清除" } ?? "已清除无效的食材用量或单位"
        case "ingredient_dropped_malformed":
            return params["index"].map { "第 \($0) 项食材信息不完整，已省略" } ?? "已省略信息不完整的食材"
        case "step_dropped_malformed":
            return params["index"].map { "第 \($0) 步信息不完整，已省略" } ?? "已省略信息不完整的步骤"
        default:
            return warningText(warning) ?? "AI 结果包含一条提示，请检查内容。"
        }
    }

    static func intakeWarning(_ warning: AIWarning) -> String {
        let params = warning.params
        let index = params["index"].map(JSONValue.string)
        let field = params["field"].map(intakeField) ?? "字段"
        switch warning.code {
        case "locale_fallback":
            return aiWarning(warning)
        case "op_invalid":
            return "\(indexedLabel("操作", counter: "条", index: index))无效，已忽略"
        case "op_target_unknown":
            return "\(indexedLabel("操作", counter: "条", index: index))找不到对应条目，已忽略"
        case "op_conflict":
            return "\(indexedLabel("操作", counter: "条", index: index))的条目已删除，已忽略更新"
        case "ops_dropped":
            return params["count"].map { "已忽略 \($0) 条无效操作" } ?? "已忽略无效操作"
        case "op_field_dropped":
            return "\(indexedLabel("操作", counter: "条", index: index))中不允许修改\(field)"
        case "field_value_dropped":
            return "\(field)无效，已清除"
        case "quantity_dropped":
            return "数量无效，已清除"
        case "category_dropped":
            return "找不到对应分类，请选择分类"
        case "date_dropped":
            return "\(field)的日期无效，请检查"
        case "expiration_moved_to_suggested":
            return "未确认的到期日已作为建议保留"
        case "expiration_date_inferred":
            return params["basis"] == "category_default" ? "按分类默认保质期建议到期日" : "已生成建议到期日"
        case "ai_expiration_ignored":
            return params["date"].map { "已忽略推测的到期日（\($0)）" } ?? "已忽略推测的到期日"
        case "expiration_before_purchase":
            return "到期日在购买日期之前，请检查"
        case "printed_date_unclear":
            return "商品标签上的日期不明确，请检查"
        case "printed_evidence_dropped":
            return "无法使用这张图片上的日期标签"
        case "quantity_value_inferred":
            return "照片中的数量为估计值，请检查"
        case "restock_match_dropped":
            return "关联的补货条目已不可用"
        case "restock_already_done":
            return "物品已入库，补货条目之前已完成"
        case "duplicate_generic_line":
            return "小票上有同名条目，请分别核对"
        case "purchase_date_from_receipt":
            return "购买日期来自小票"
        case "quantity_unit_inferred":
            return "数量单位为推测值，请检查"
        case "location_inferred":
            return "存放位置为推测值，请检查"
        default:
            return warningText(warning) ?? "入库结果包含一条提示，请检查内容。"
        }
    }

    static func intakeSource(_ source: IntakeSource) -> String? {
        let title: String
        switch source.inputKind {
        case "receipt": title = "小票"
        case "product_closeup": title = "商品特写"
        case "product_overview": title = "整体照片"
        default: return nil
        }
        guard let index = source.imageIndex, index >= 0, index < Int.max else { return title }
        return "\(title) · 第 \(index + 1) 张"
    }

    static func intakeField(_ code: String) -> String {
        switch code {
        case "name": "名称"
        case "category_id": "分类"
        case "quantity_value": "数量"
        case "quantity_unit": "数量单位"
        case "owner": "所有者"
        case "location": "存放位置"
        case "purchase_date": "购买日期"
        case "unopened_expiration_date": "未开封到期日"
        case "suggested_unopened_expiration_date": "建议到期日"
        case "opened_expiration_date": "开封后到期日"
        case "opened_date": "开封日期"
        case "expiration_source": "到期日来源"
        case "matched_restock_id": "补货关联"
        case "restock_action": "补货操作"
        case "notes": "备注"
        default: "字段"
        }
    }

    private static func warningText(_ warning: AIWarning) -> String? {
        warning.message?.nilIfBlank ?? warning.detail?.nilIfBlank
    }

    static func difficulty(_ code: String) -> String {
        switch code {
        case "easy": "简单"
        case "medium": "中等"
        case "hard": "困难"
        default: code
        }
    }

    static func cookingMethod(_ code: String) -> String {
        switch code {
        case "stir_fry": "炒"
        case "steam": "蒸"
        case "boil": "煮"
        case "braise": "焖"
        case "stew": "炖"
        case "pan_fry": "煎"
        case "deep_fry": "炸"
        case "roast": "烤"
        case "bake": "烘焙"
        case "grill": "烧烤"
        case "cold_mix": "凉拌"
        case "raw": "生食"
        case "other": "其他做法"
        default: code
        }
    }

    static func cuisineGroup(_ code: String) -> String {
        switch code {
        case "chinese": "中式"
        case "japanese": "日式"
        case "korean": "韩式"
        case "western": "西式"
        case "southeast_asian": "东南亚"
        case "other": "其他菜系"
        default: code
        }
    }

    private static func aiField(_ code: String) -> String {
        switch code {
        case "category": "分类"
        case "difficulty": "难度"
        case "servings": "份量"
        case "cook_time_minutes", "estimated_time_minutes": "烹饪时间"
        case "cooking_method": "做法"
        case "cuisine_group", "cuisine": "菜系"
        case "flavors": "口味"
        case "textures": "口感"
        case "missing_ingredients": "缺少的食材"
        default: "字段"
        }
    }

    static func recipeUsage(_ code: String) -> String {
        switch code {
        case "always": "始终用于菜谱"
        case "conditional": "按条件用于菜谱"
        case "never": "不用于菜谱"
        default: code
        }
    }

    private static func indexedLabel(_ label: String, counter: String, index: JSONValue?) -> String {
        guard let index = index?.text.flatMap(Int.init), (0..<Int.max).contains(index) else { return label }
        return "第 \(index + 1) \(counter)\(label)"
    }
}
