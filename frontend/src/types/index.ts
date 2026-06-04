export interface Item {
  id: number;
  name: string;
  category: string;
  owner: string;
  purchase_date: string;
  quantity_value: number;
  quantity_unit: string;
  location: string;
  unopened_expiration_date: string;
  opened_expiration_date: string | null;
  opened_date: string | null;
  current_expiration_date: string;
  status: 'active' | 'consumed' | 'expiring soon' | 'expired';
  notes: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ItemCreate {
  name: string;
  category: string;
  owner: string;
  purchase_date?: string;
  quantity_value: number;
  quantity_unit: string;
  location: string;
  unopened_expiration_date: string;
  opened_expiration_date?: string | null;
  opened_date?: string | null;
  current_expiration_date: string;
  notes?: string | null;
}

export interface ItemUpdate {
  name?: string;
  category?: string;
  owner?: string;
  purchase_date?: string;
  quantity_value?: number;
  quantity_unit?: string;
  location?: string;
  unopened_expiration_date?: string;
  opened_expiration_date?: string | null;
  opened_date?: string | null;
  current_expiration_date?: string;
  notes?: string | null;
}

export interface ConsumeRequest {
  quantity: number;
  add_to_restock: boolean;
}

export interface RestockItem {
  id: number;
  name: string;
  category: string | null;
  quantity_value: number | null;
  quantity_unit: string | null;
  source_item_id: number | null;
  status: 'pending' | 'done';
  notes: string | null;
  created_at?: string;
  done_at?: string | null;
}

export interface RestockItemCreate {
  name: string;
  category?: string;
  quantity_value?: number;
  quantity_unit?: string;
  source_item_id?: number;
  notes?: string;
}

export interface RestockItemUpdate {
  name?: string;
  category?: string;
  quantity_value?: number;
  quantity_unit?: string;
  status?: string;
  notes?: string;
}

export interface RestockDoneRequest {
  purchased_quantity: number;
  owner?: string;
  purchase_date?: string;
  location?: string;
  unopened_expiration_date?: string;
  opened_expiration_date?: string | null;
  opened_date?: string | null;
}

export interface Settings {
  default_database: string;
  expiration_reminder_days: string;
}

export interface HealthResponse {
  status: string;
  version: string;
}

// ─── Recipe Types ──────────────────────────────────────────────

export type RecipeSourceType = 'howtocook' | 'user' | 'ai_saved';

export interface RecipeIngredient {
  ingredient_name: string;
  normalized_name?: string;
  quantity?: string;
  unit?: string;
  is_optional?: boolean;
  is_seasoning?: boolean;
  sort_order?: number;
}

export interface RecipeStep {
  step_number: number;
  instruction: string;
}

export interface RecipeSummary {
  id: number;
  source_type: RecipeSourceType;
  source_name: string;
  title: string;
  category: string | null;
  difficulty: string | null;
  cook_time_minutes: number | null;
  is_user_created: boolean;
  base_recipe_id: number | null;
  is_favorite: boolean;
  has_been_cooked: boolean;
  created_at: string;
}

export interface RecipeResponse extends RecipeSummary {
  source_url?: string;
  source_path?: string;
  license_name?: string;
  description: string | null;
  servings: string | null;
  raw_markdown?: string;
  ingredients: RecipeIngredient[];
  steps: RecipeStep[];
  updated_at?: string;
}

export interface RecipeCreate {
  title: string;
  category?: string | null;
  description?: string | null;
  difficulty?: string | null;
  servings?: string | null;
  cook_time_minutes?: number | null;
  ingredients?: { ingredient_name: string; quantity?: string; unit?: string; is_optional?: boolean; is_seasoning?: boolean }[];
  steps?: { step_number: number; instruction: string }[];
}

export interface RecipeUpdate {
  title?: string;
  category?: string | null;
  description?: string | null;
  difficulty?: string | null;
  servings?: string | null;
  cook_time_minutes?: number | null;
  ingredients?: { ingredient_name: string; quantity?: string; unit?: string; is_optional?: boolean; is_seasoning?: boolean }[];
  steps?: { step_number: number; instruction: string }[];
}

export interface RecipeRecommendation {
  recipe_id: number;
  title: string;
  score: number;
  reason: string;
  matched_inventory_items: string[];
  expiring_inventory_items: string[];
  missing_ingredients: string[];
  is_favorite: boolean;
  is_new_suggestion: boolean;
  source_type: RecipeSourceType;
}

export interface AIRecommendation {
  title: string;
  reason: string;
  recipe_id: number;
}

export interface ConsumeSuggestionItem {
  ingredient_name: string;
  item_id: number;
  item_name: string;
  available_quantity: number;
  suggested_quantity: number;
  status: 'active' | 'expiring soon';
}

export interface ConsumePreview {
  recipe_id: number;
  title: string;
  suggestions: ConsumeSuggestionItem[];
  unmatched_ingredients: string[];
}

export interface CookConsumedItem {
  item_id: number;
  item_name: string;
  consumed_quantity: number;
  remaining_quantity: number;
  status: string;
}

export interface CookResponse {
  message: string;
  recipe_id: number;
  consumed_items: CookConsumedItem[];
  notes: string | null;
}

export interface RecipeSource {
  attribution: string;
  repository: string;
  license: string;
}

// ─── Explore Recipe Types ──────────────────────────────────────────

export type ExploreMode = 'structured' | 'natural_language';

export interface ExploreStructuredPreferences {
  cuisine?: string | null;
  flavor?: string | null;
  texture?: string | null;
  main_ingredient?: string | null;
  avoid_ingredients?: string[] | null;
  meal_type?: string | null;
  max_cook_time_minutes?: number | null;
}

export interface ExploreIdea {
  recipe_id?: number | null;
  title: string;
  description?: string | null;
  matched_ingredients?: string[];
  expiring_ingredients?: string[];
  missing_ingredients?: string[];
  cuisine?: string | null;
  flavor?: string | null;
  texture?: string | null;
  can_expand_to_recipe?: boolean;
}

export interface ExploreRequest {
  mode: ExploreMode;
  structured?: ExploreStructuredPreferences | null;
  natural_language?: string | null;
}

export interface ExploreResponse {
  mode: 'ai';
  input_mode: ExploreMode;
  ideas: ExploreIdea[];
  warnings: string[];
}
