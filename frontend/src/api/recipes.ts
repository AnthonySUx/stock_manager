import api from './client';
import type {
  RecipeSummary,
  RecipeResponse,
  RecipeCreate,
  RecipeUpdate,
  RecipeRecommendation,
  AIRecommendation,
  ConsumePreview,
  CookResponse,
  RecipeSource,
} from '../types';
import mockApi from './mockRecipes';

// Set to true to use mock data (no backend needed for recipe debugging)
// Set to false to call the real backend API
const USE_MOCK = true;

export interface RecipeListParams {
  source_type?: string;
  category?: string;
  query?: string;
  favorite_only?: boolean;
  limit?: number;
  offset?: number;
}

// Conditional wrapper: when USE_MOCK is true, delegate to mockApi
const wrap = <T>(mockFn: () => Promise<{ data: T }>, realFn: () => Promise<{ data: T }>): Promise<{ data: T }> => {
  return USE_MOCK ? mockFn() : realFn();
};

export const recipesApi = {
  list(params?: RecipeListParams) {
    return wrap(
      () => mockApi.list(params),
      () => api.get<RecipeSummary[]>('/recipes', { params })
    );
  },

  get(id: number) {
    return wrap(
      () => mockApi.get(id),
      () => api.get<RecipeResponse>(`/recipes/${id}`)
    );
  },

  create(data: RecipeCreate) {
    return wrap(
      () => mockApi.create(data),
      () => api.post<RecipeResponse>('/recipes', data)
    );
  },

  update(id: number, data: RecipeUpdate) {
    return wrap(
      () => mockApi.update(id, data),
      () => api.patch<RecipeResponse>(`/recipes/${id}`, data)
    );
  },

  delete(id: number) {
    return wrap(
      () => mockApi.delete(id),
      () => api.delete(`/recipes/${id}`)
    );
  },

  fork(id: number) {
    return wrap(
      () => mockApi.fork(id),
      () => api.post<RecipeResponse>(`/recipes/${id}/fork`)
    );
  },

  addFavorite(id: number) {
    return wrap(
      () => mockApi.addFavorite(id),
      () => api.post(`/recipes/${id}/favorite`)
    );
  },

  removeFavorite(id: number) {
    return wrap(
      () => mockApi.removeFavorite(id),
      () => api.delete(`/recipes/${id}/favorite`)
    );
  },

  recommendations(params?: { limit?: number; include_expired?: boolean }) {
    return wrap(
      () => mockApi.recommendations(params),
      () => api.get<RecipeRecommendation[]>('/recipes/recommendations', { params })
    );
  },

  aiToday(params?: { limit?: number }) {
    return wrap(
      () => mockApi.aiToday(params),
      () => api.post<{ recommendations: AIRecommendation[] }>('/recipes/ai/today', null, { params })
    );
  },

  sources() {
    return wrap(
      () => mockApi.sources(),
      () => api.get<RecipeSource>('/recipes/sources')
    );
  },

  consumePreview(id: number) {
    return wrap(
      () => mockApi.consumePreview(id),
      () => api.get<ConsumePreview>(`/recipes/${id}/consume-preview`)
    );
  },

  cook(
    id: number,
    data: { consume_items: { item_id: number; quantity: number }[]; notes?: string | null }
  ) {
    return wrap(
      () => mockApi.cook(id, data),
      () => api.post<CookResponse>(`/recipes/${id}/cook`, data)
    );
  },
};
