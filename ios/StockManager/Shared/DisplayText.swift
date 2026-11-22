enum DisplayText {
    static let restockAlreadyDone = "补货已完成"

    static func error(_ code: String, params: [String: JSONValue] = [:]) -> String {
        let max = params["max"]?.text
        switch code {
        case "ai_unavailable": return "AI 功能未开启"
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
        default: return code
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
