enum DisplayText {
    static let restockAlreadyDone = "这条补货之前已经入库，无需重复操作"
    static let aiUnavailable = "AI 功能未开启"
    static let recipeDifficulties = ["easy", "medium", "hard"]

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
            return warning.message?.nilIfBlank ?? warning.detail?.nilIfBlank ?? "AI 结果包含一条提示，请检查内容。"
        }
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
