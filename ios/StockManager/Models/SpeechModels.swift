enum SpeechFeature: String {
    case stockIntake = "stock_intake"
    case recipeExplore = "recipe_explore"
}

struct SpeechTranscription: Decodable {
    let transcript: String
    let durationMs: Int
}
