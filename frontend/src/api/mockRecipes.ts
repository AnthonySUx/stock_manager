import type {
  RecipeSummary,
  RecipeResponse,
  RecipeRecommendation,
  AIRecommendation,
  ConsumePreview,
  CookResponse,
  RecipeSource,
  ExploreIdea,
  ExploreRequest,
  ExploreResponse,
} from '../types';

// ── Mock Recipes Data ──────────────────────────────────────────────
// Fields match the backend API reference exactly.

interface MockData {
  recipes: RecipeResponse[];
  favorites: Set<number>;
  cooked: Set<number>;
  lastId: number;
}

const data: MockData = {
  recipes: [
    {
      // Recipe 1 — HowToCook, tomato & egg
      id: 1,
      source_type: 'howtocook',
      source_name: 'HowToCook',
      title: '番茄炒蛋',
      category: '热菜',
      difficulty: 'easy',
      cook_time_minutes: 15,
      is_user_created: false,
      base_recipe_id: null,
      is_favorite: true,
      has_been_cooked: true,
      created_at: '2024-01-15T08:00:00Z',
      source_url: 'https://github.com/Anduin2017/HowToCook',
      source_path: 'dishes/meat_dish/番茄炒蛋.md',
      license_name: 'The Unlicense',
      description: '经典家常菜，番茄酸甜搭配鸡蛋嫩滑，简单快手。',
      servings: '2 人份',
      
      ingredients: [
        { ingredient_name: '番茄', normalized_name: '番茄', quantity: '2', unit: '个', is_optional: false, is_seasoning: false, sort_order: 1 },
        { ingredient_name: '鸡蛋', normalized_name: '鸡蛋', quantity: '3', unit: '个', is_optional: false, is_seasoning: false, sort_order: 2 },
        { ingredient_name: '葱', normalized_name: '葱', quantity: '1', unit: '根', is_optional: false, is_seasoning: true, sort_order: 3 },
        { ingredient_name: '盐', normalized_name: '盐', quantity: '1', unit: '茶匙', is_optional: false, is_seasoning: true, sort_order: 4 },
        { ingredient_name: '糖', normalized_name: '糖', quantity: '1', unit: '茶匙', is_optional: false, is_seasoning: true, sort_order: 5 },
        { ingredient_name: '食用油', normalized_name: '食用油', quantity: '15', unit: '毫升', is_optional: false, is_seasoning: true, sort_order: 6 },
      ],
      steps: [
        { step_number: 1, instruction: '番茄洗净切块，鸡蛋打散加少许盐搅匀。' },
        { step_number: 2, instruction: '热锅凉油，倒入蛋液，炒至凝固后盛出备用。' },
        { step_number: 3, instruction: '锅中再加少许油，放入番茄块翻炒至出汁。' },
        { step_number: 4, instruction: '加入炒好的鸡蛋，放入盐和糖调味，翻炒均匀。' },
        { step_number: 5, instruction: '撒上葱花，出锅装盘。' },
      ],
      updated_at: '2024-01-15T08:00:00Z',
    },
    {
      // Recipe 2 — User created, chicken salad
      id: 2,
      source_type: 'user',
      source_name: '我的菜谱',
      title: '鸡胸肉沙拉',
      category: '凉菜',
      difficulty: 'easy',
      cook_time_minutes: 20,
      is_user_created: true,
      base_recipe_id: null,
      is_favorite: false,
      has_been_cooked: false,
      created_at: '2025-03-10T14:30:00Z',
      source_url: undefined,
      source_path: undefined,
      license_name: undefined,
      description: '低卡高蛋白，健身减脂必备。',
      servings: '1 人份',
      
      ingredients: [
        { ingredient_name: '鸡胸肉', normalized_name: '鸡胸肉', quantity: '1', unit: '块', is_optional: false, is_seasoning: false, sort_order: 1 },
        { ingredient_name: '生菜', normalized_name: '生菜', quantity: '100', unit: '克', is_optional: false, is_seasoning: false, sort_order: 2 },
        { ingredient_name: '圣女果', normalized_name: '圣女果', quantity: '6', unit: '个', is_optional: false, is_seasoning: false, sort_order: 3 },
        { ingredient_name: '玉米粒', normalized_name: '玉米粒', quantity: '50', unit: '克', is_optional: true, is_seasoning: false, sort_order: 4 },
        { ingredient_name: '橄榄油', normalized_name: '橄榄油', quantity: '10', unit: '毫升', is_optional: false, is_seasoning: true, sort_order: 5 },
        { ingredient_name: '柠檬汁', normalized_name: '柠檬汁', quantity: '5', unit: '毫升', is_optional: false, is_seasoning: true, sort_order: 6 },
        { ingredient_name: '黑胡椒', normalized_name: '黑胡椒', quantity: '适量', unit: '', is_optional: false, is_seasoning: true, sort_order: 7 },
        { ingredient_name: '盐', normalized_name: '盐', quantity: '适量', unit: '', is_optional: false, is_seasoning: true, sort_order: 8 },
      ],
      steps: [
        { step_number: 1, instruction: '鸡胸肉用盐和黑胡椒腌制 10 分钟。' },
        { step_number: 2, instruction: '平底锅加少许橄榄油，中小火煎鸡胸肉至两面金黄熟透（约 8 分钟）。' },
        { step_number: 3, instruction: '生菜洗净撕成小片，圣女果对半切开。' },
        { step_number: 4, instruction: '玉米粒焯水后沥干。' },
        { step_number: 5, instruction: '所有食材放入碗中，淋上柠檬汁和橄榄油，拌匀即可。' },
      ],
      updated_at: '2025-03-10T14:30:00Z',
    },
    {
      // Recipe 3 — AI saved, potato beef rice
      id: 3,
      source_type: 'ai_saved',
      source_name: 'AI 建议',
      title: '土豆牛肉焖饭',
      category: '主食',
      difficulty: 'medium',
      cook_time_minutes: 45,
      is_user_created: false,
      base_recipe_id: null,
      is_favorite: false,
      has_been_cooked: false,
      created_at: '2025-02-20T10:00:00Z',
      source_url: undefined,
      source_path: undefined,
      license_name: undefined,
      description: '一锅出的懒人焖饭，土豆软糯牛肉香嫩，适合忙碌的工作日晚餐。',
      servings: '3 人份',
      
      ingredients: [
        { ingredient_name: '土豆', normalized_name: '土豆', quantity: '2', unit: '个', is_optional: false, is_seasoning: false, sort_order: 1 },
        { ingredient_name: '牛肉', normalized_name: '牛肉', quantity: '200', unit: '克', is_optional: false, is_seasoning: false, sort_order: 2 },
        { ingredient_name: '大米', normalized_name: '大米', quantity: '1.5', unit: '杯', is_optional: false, is_seasoning: false, sort_order: 3 },
        { ingredient_name: '胡萝卜', normalized_name: '胡萝卜', quantity: '1', unit: '根', is_optional: false, is_seasoning: false, sort_order: 4 },
        { ingredient_name: '洋葱', normalized_name: '洋葱', quantity: '0.5', unit: '个', is_optional: false, is_seasoning: false, sort_order: 5 },
        { ingredient_name: '生抽', normalized_name: '生抽', quantity: '2', unit: '汤匙', is_optional: false, is_seasoning: true, sort_order: 6 },
        { ingredient_name: '老抽', normalized_name: '老抽', quantity: '1', unit: '汤匙', is_optional: false, is_seasoning: true, sort_order: 7 },
        { ingredient_name: '食用油', normalized_name: '食用油', quantity: '适量', unit: '', is_optional: false, is_seasoning: true, sort_order: 8 },
      ],
      steps: [
        { step_number: 1, instruction: '牛肉切小块，用生抽腌制 15 分钟。' },
        { step_number: 2, instruction: '土豆、胡萝卜去皮切丁，洋葱切丝。' },
        { step_number: 3, instruction: '热锅加油，炒香洋葱后加入牛肉翻炒至变色。' },
        { step_number: 4, instruction: '加入土豆丁和胡萝卜丁，加生抽老抽翻炒均匀。' },
        { step_number: 5, instruction: '大米淘洗干净放入电饭煲，倒入炒好的食材，加适量水。' },
        { step_number: 6, instruction: '按煮饭键，煮好后焖 5 分钟，拌匀即可。' },
      ],
      updated_at: '2025-02-20T10:00:00Z',
    },
    {
      // Recipe 4 — HowToCook, green veggie tofu soup
      id: 4,
      source_type: 'howtocook',
      source_name: 'HowToCook',
      title: '青菜豆腐汤',
      category: '汤羹',
      difficulty: 'easy',
      cook_time_minutes: 10,
      is_user_created: false,
      base_recipe_id: null,
      is_favorite: false,
      has_been_cooked: false,
      created_at: '2024-06-01T12:00:00Z',
      source_url: 'https://github.com/Anduin2017/HowToCook',
      source_path: 'dishes/soup/青菜豆腐汤.md',
      license_name: 'The Unlicense',
      description: '清淡鲜美，五分钟就能做好的快手汤。',
      servings: '2 人份',
      
      ingredients: [
        { ingredient_name: '青菜', normalized_name: '青菜', quantity: '200', unit: '克', is_optional: false, is_seasoning: false, sort_order: 1 },
        { ingredient_name: '嫩豆腐', normalized_name: '豆腐', quantity: '1', unit: '块', is_optional: false, is_seasoning: false, sort_order: 2 },
        { ingredient_name: '盐', normalized_name: '盐', quantity: '1', unit: '茶匙', is_optional: false, is_seasoning: true, sort_order: 3 },
        { ingredient_name: '香油', normalized_name: '香油', quantity: '几滴', unit: '', is_optional: false, is_seasoning: true, sort_order: 4 },
      ],
      steps: [
        { step_number: 1, instruction: '青菜洗净切段，豆腐切成小方块。' },
        { step_number: 2, instruction: '锅中烧水，水开后放入豆腐煮 2 分钟。' },
        { step_number: 3, instruction: '放入青菜，煮至青菜变软（约 1 分钟）。' },
        { step_number: 4, instruction: '加盐调味，滴几滴香油，关火出锅。' },
      ],
      updated_at: '2024-06-01T12:00:00Z',
    },
    {
      // Recipe 5 — User created, fork base from recipe 1
      id: 5,
      source_type: 'user',
      source_name: '我的菜谱',
      title: '番茄炒蛋（改良版）',
      category: '热菜',
      difficulty: 'easy',
      cook_time_minutes: 12,
      is_user_created: true,
      base_recipe_id: 1,
      is_favorite: true,
      has_been_cooked: true,
      created_at: '2025-04-01T09:00:00Z',
      source_url: undefined,
      source_path: undefined,
      license_name: undefined,
      description: '加了番茄酱的改良版，番茄味更浓郁。',
      servings: '2 人份',
      
      ingredients: [
        { ingredient_name: '番茄', normalized_name: '番茄', quantity: '3', unit: '个', is_optional: false, is_seasoning: false, sort_order: 1 },
        { ingredient_name: '鸡蛋', normalized_name: '鸡蛋', quantity: '3', unit: '个', is_optional: false, is_seasoning: false, sort_order: 2 },
        { ingredient_name: '番茄酱', normalized_name: '番茄酱', quantity: '1', unit: '汤匙', is_optional: false, is_seasoning: true, sort_order: 3 },
        { ingredient_name: '葱', normalized_name: '葱', quantity: '1', unit: '根', is_optional: false, is_seasoning: true, sort_order: 4 },
        { ingredient_name: '盐', normalized_name: '盐', quantity: '1', unit: '茶匙', is_optional: false, is_seasoning: true, sort_order: 5 },
        { ingredient_name: '糖', normalized_name: '糖', quantity: '0.5', unit: '茶匙', is_optional: false, is_seasoning: true, sort_order: 6 },
        { ingredient_name: '食用油', normalized_name: '食用油', quantity: '15', unit: '毫升', is_optional: false, is_seasoning: true, sort_order: 7 },
      ],
      steps: [
        { step_number: 1, instruction: '番茄切小块，鸡蛋打散加少许盐。' },
        { step_number: 2, instruction: '热锅凉油，炒好鸡蛋盛出。' },
        { step_number: 3, instruction: '锅中加油炒番茄，加入番茄酱炒出红油。' },
        { step_number: 4, instruction: '倒回鸡蛋，加盐和糖调味，撒葱花出锅。' },
      ],
      updated_at: '2025-04-01T09:00:00Z',
    },
  ],
  favorites: new Set<number>([1, 5]),
  cooked: new Set<number>([1, 5]),
  lastId: 5,
};

// ── Helper Functions ────────────────────────────────────────────────

function toSummary(r: RecipeResponse): RecipeSummary {
  const { source_url, source_path, license_name, description, servings, raw_markdown, ingredients, steps, updated_at, ...summary } = r;
  return summary;
}

function filterRecipes(params: {
  source_type?: string;
  category?: string;
  query?: string;
  favorite_only?: boolean;
  limit?: number;
  offset?: number;
}): RecipeSummary[] {
  let results = data.recipes.slice();

  if (params.source_type) {
    results = results.filter((r) => r.source_type === params.source_type);
  }
  if (params.category) {
    results = results.filter((r) => r.category === params.category);
  }
  if (params.favorite_only) {
    results = results.filter((r) => data.favorites.has(r.id));
  }
  if (params.query) {
    const q = params.query.toLowerCase();
    results = results.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        r.ingredients.some((i) => i.ingredient_name.toLowerCase().includes(q)) ||
        (r.description && r.description.toLowerCase().includes(q))
    );
  }

  // Simulate backend sort: favorites > cooked > user-created > by id
  results.sort((a, b) => {
    const aFav = data.favorites.has(a.id) ? 1 : 0;
    const bFav = data.favorites.has(b.id) ? 1 : 0;
    if (aFav !== bFav) return bFav - aFav;
    const aCook = data.cooked.has(a.id) ? 1 : 0;
    const bCook = data.cooked.has(b.id) ? 1 : 0;
    if (aCook !== bCook) return bCook - aCook;
    if (a.is_user_created !== b.is_user_created) return a.is_user_created ? -1 : 1;
    return a.id - b.id;
  });

  const limit = params.limit ?? 20;
  const offset = params.offset ?? 0;
  return results.slice(offset, offset + limit).map(toSummary);
}

function findRecipe(id: number): RecipeResponse | undefined {
  return data.recipes.find((r) => r.id === id);
}

// ── Mock API ────────────────────────────────────────────────────────

const mockApi = {
  list(params?: any) {
    return Promise.resolve({ data: filterRecipes(params || {}) });
  },

  get(id: number) {
    const recipe = findRecipe(id);
    if (!recipe) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });
    return Promise.resolve({ data: { ...recipe, is_favorite: data.favorites.has(id), has_been_cooked: data.cooked.has(id) } });
  },

  create(input: any) {
    const id = data.lastId + 1;
    data.lastId = id;
    const now = new Date().toISOString();
    const newRecipe: RecipeResponse = {
      id,
      source_type: 'user',
      source_name: '我的菜谱',
      title: input.title || '未命名菜谱',
      category: input.category || null,
      difficulty: input.difficulty || null,
      cook_time_minutes: input.cook_time_minutes ?? null,
      is_user_created: true,
      base_recipe_id: null,
      is_favorite: false,
      has_been_cooked: false,
      created_at: now,
      source_url: undefined,
      source_path: undefined,
      license_name: undefined,
      description: input.description || null,
      servings: input.servings || null,
      ingredients: (input.ingredients || []).map((i: any, idx: number) => ({
        ingredient_name: i.ingredient_name,
        normalized_name: i.ingredient_name,
        quantity: i.quantity || null,
        unit: i.unit || null,
        is_optional: i.is_optional || false,
        is_seasoning: i.is_seasoning || false,
        sort_order: idx + 1,
      })),
      steps: (input.steps || []).map((s: any) => ({
        step_number: s.step_number,
        instruction: s.instruction,
      })),
      updated_at: now,
    };
    data.recipes.push(newRecipe);
    return Promise.resolve({ data: newRecipe });
  },

  update(id: number, data: any) {
    const recipe = findRecipe(id);
    if (!recipe) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });
    if (recipe.source_type === 'howtocook') return Promise.reject({ response: { status: 403, data: { detail: 'HowToCook recipes are read-only' } } });

    const now = new Date().toISOString();
    Object.assign(recipe, {
      title: data.title ?? recipe.title,
      category: data.category !== undefined ? data.category : recipe.category,
      description: data.description !== undefined ? data.description : recipe.description,
      difficulty: data.difficulty !== undefined ? data.difficulty : recipe.difficulty,
      servings: data.servings !== undefined ? data.servings : recipe.servings,
      cook_time_minutes: data.cook_time_minutes !== undefined ? data.cook_time_minutes : recipe.cook_time_minutes,
      updated_at: now,
    });
    if (data.ingredients) {
      recipe.ingredients = data.ingredients.map((i: any, idx: number) => ({
        ingredient_name: i.ingredient_name,
        normalized_name: i.ingredient_name,
        quantity: i.quantity || null,
        unit: i.unit || null,
        is_optional: i.is_optional || false,
        is_seasoning: i.is_seasoning || false,
        sort_order: idx + 1,
      }));
    }
    if (data.steps) {
      recipe.steps = data.steps.map((s: any) => ({
        step_number: s.step_number,
        instruction: s.instruction,
      }));
    }
    return Promise.resolve({ data: recipe });
  },

  delete(id: number) {
    const idx = data.recipes.findIndex((r) => r.id === id);
    if (idx === -1) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });
    if (data.recipes[idx].source_type === 'howtocook') return Promise.reject({ response: { status: 403, data: { detail: 'HowToCook recipes cannot be deleted' } } });
    data.recipes.splice(idx, 1);
    data.favorites.delete(id);
    data.cooked.delete(id);
    return Promise.resolve({ data: { detail: 'Deleted' } });
  },

  fork(id: number) {
    const original = findRecipe(id);
    if (!original) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });
    data.lastId += 1;
    const now = new Date().toISOString();
    const forked: RecipeResponse = {
      ...original,
      id: data.lastId,
      source_type: 'user',
      source_name: '我的菜谱',
      base_recipe_id: original.id,
      is_user_created: true,
      is_favorite: false,
      has_been_cooked: false,
      created_at: now,
      updated_at: now,
      source_url: undefined,
      source_path: undefined,
      license_name: undefined,
    };
    data.recipes.push(forked);
    return Promise.resolve({ data: forked });
  },

  addFavorite(id: number) {
    if (!findRecipe(id)) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });
    data.favorites.add(id);
    return Promise.resolve({ data: { detail: 'Favorited' } });
  },

  removeFavorite(id: number) {
    if (!findRecipe(id)) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });
    data.favorites.delete(id);
    return Promise.resolve({ data: { detail: 'Unfavorited' } });
  },

  recommendations(params?: { limit?: number; include_expired?: boolean }) {
    const limit = params?.limit ?? 10;
    const mockRecs: RecipeRecommendation[] = [
      {
        recipe_id: 1,
        title: '番茄炒蛋',
        score: 35,
        reason: '库存中有番茄和鸡蛋，完美匹配',
        matched_inventory_items: ['番茄', '鸡蛋'],
        expiring_inventory_items: [],
        missing_ingredients: ['葱'],
        is_favorite: true,
        is_new_suggestion: false,
        source_type: 'howtocook',
      },
      {
        recipe_id: 2,
        title: '鸡胸肉沙拉',
        score: 50,
        reason: '鸡胸肉即将到期，建议尽快食用',
        matched_inventory_items: ['鸡胸肉'],
        expiring_inventory_items: ['鸡胸肉'],
        missing_ingredients: ['圣女果', '生菜'],
        is_favorite: false,
        is_new_suggestion: true,
        source_type: 'user',
      },
      {
        recipe_id: 4,
        title: '青菜豆腐汤',
        score: 20,
        reason: '库存有青菜和豆腐',
        matched_inventory_items: ['青菜', '豆腐'],
        expiring_inventory_items: [],
        missing_ingredients: [],
        is_favorite: false,
        is_new_suggestion: false,
        source_type: 'howtocook',
      },
    ];
    return Promise.resolve({ data: mockRecs.slice(0, limit) });
  },

  aiToday(params?: { limit?: number }) {
    const limit = params?.limit ?? 15;
    const mockAi: AIRecommendation[] = [
      { title: '番茄炒蛋', reason: '今日推荐经典家常菜，简单快手', recipe_id: 1 },
      { title: '青菜豆腐汤', reason: '清淡解腻，适合搭配晚餐', recipe_id: 4 },
    ];
    return Promise.resolve({
      data: {
        recommendations: mockAi.slice(0, limit),
        ai_config: { base_url: 'https://api.deepseek.com', model: 'deepseek-chat' },
      },
    });
  },

  sources() {
    const source: RecipeSource = {
      attribution: 'HowToCook - Anduin2017/HowToCook',
      repository: 'https://github.com/Anduin2017/HowToCook',
      license: 'The Unlicense',
    };
    return Promise.resolve({ data: source });
  },

  consumePreview(id: number) {
    const recipe = findRecipe(id);
    if (!recipe) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });

    const preview: ConsumePreview = {
      recipe_id: id,
      title: recipe.title,
      suggestions: recipe.ingredients
        .filter((ing) => !ing.is_seasoning)
        .slice(0, 3)
        .map((ing, idx) => ({
          ingredient_name: ing.ingredient_name,
          item_id: idx + 100,
          item_name: ing.ingredient_name,
          available_quantity: [2, 3, 1][idx % 3] * 100,
          suggested_quantity: parseFloat(ing.quantity || '1') || 1,
          status: idx === 1 ? ('expiring soon' as const) : ('active' as const),
        })),
      unmatched_ingredients: recipe.ingredients
        .filter((ing) => !ing.is_seasoning)
        .slice(3)
        .map((ing) => ing.ingredient_name),
    };
    return Promise.resolve({ data: preview });
  },

  cook(
    id: number,
    input: { consume_items: { item_id: number; quantity: number }[]; notes?: string | null }
  ) {
    const recipe = findRecipe(id);
    if (!recipe) return Promise.reject({ response: { status: 404, data: { detail: 'Not Found' } } });

    data.cooked.add(id);
    const response: CookResponse = {
      message: `成功烹饪「${recipe.title}」！`,
      recipe_id: id,
      consumed_items: input.consume_items.map((item) => ({
        item_id: item.item_id,
        item_name: `食材 #${item.item_id}`,
        consumed_quantity: item.quantity,
        remaining_quantity: Math.max(0, 100 - item.quantity),
        status: 'active',
      })),
      notes: input.notes || null,
    };
    return Promise.resolve({ data: response });
  }
,

  explore(data: ExploreRequest) {
    const { mode, structured, natural_language } = data;
    const ideas: ExploreIdea[] = [
      {
        recipe_id: 1,
        title: '番茄炒蛋',
        description: '经典家常菜，番茄酸甜搭配鸡蛋嫩滑，简单快手。',
        matched_ingredients: ['番茄', '鸡蛋'],
        expiring_ingredients: [],
        missing_ingredients: ['葱'],
        cuisine: '中式',
        flavor: '酸甜',
        texture: '嫩滑',
        can_expand_to_recipe: true,
      },
      {
        recipe_id: null,
        title: '蒜蓉西兰花炒虾仁',
        description: '清爽低脂，蒜香浓郁，搭配鲜嫩虾仁，营养均衡。',
        matched_ingredients: ['西兰花', '虾仁'],
        expiring_ingredients: ['虾仁'],
        missing_ingredients: ['大蒜', '料酒'],
        cuisine: '中式',
        flavor: '蒜香',
        texture: '清爽',
        can_expand_to_recipe: true,
      },
      {
        recipe_id: 2,
        title: '鸡胸肉沙拉',
        description: '低卡高蛋白，健身减脂必备。',
        matched_ingredients: ['鸡胸肉'],
        expiring_ingredients: [],
        missing_ingredients: [],
        cuisine: '西式',
        flavor: '清淡',
        texture: '爽口',
        can_expand_to_recipe: false,
      },
    ];
    const warnings: string[] = [];
    if (mode === 'natural_language' && natural_language && natural_language.length < 3) {
      warnings.push('输入的文本较短，建议提供更多描述以获得更准确的推荐。');
    }
    if (mode === 'structured' && structured && !structured.cuisine && !structured.main_ingredient) {
      warnings.push('未指定菜系或主要食材，推荐结果可能不够精准。');
    }
    const response: ExploreResponse = {
      mode: 'ai',
      input_mode: mode,
      ideas,
      warnings,
    };
    return Promise.resolve({ data: response });
  }
};

export default mockApi;
