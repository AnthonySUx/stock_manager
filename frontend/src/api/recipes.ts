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

export interface RecipeListParams {
  source_type?: string;
  category?: string;
  query?: string;
  favorite_only?: boolean;
  limit?: number;
  offset?: number;
}

export const recipesApi = {
  list(params?: RecipeListParams) {
    return api.get<RecipeSummary[]>('/recipes', { params });
  },

  get(id: number) {
    return api.get<RecipeResponse>(`/recipes/${id}`);
  },

  create(data: RecipeCreate) {
    return api.post<RecipeResponse>('/recipes', data);
  },

  update(id: number, data: RecipeUpdate) {
    return api.patch<RecipeResponse>(`/recipes/${id}`, data);
  },

  delete(id: number) {
    return api.delete(`/recipes/${id}`);
  },

  fork(id: number) {
    return api.post<RecipeResponse>(`/recipes/${id}/fork`);
  },

  addFavorite(id: number) {
    return api.post(`/recipes/${id}/favorite`);
  },

  removeFavorite(id: number) {
    return api.delete(`/recipes/${id}/favorite`);
  },

  recommendations(params?: { limit?: number; include_expired?: boolean }) {
    return api.get<RecipeRecommendation[]>('/recipes/recommendations', { params });
  },

  aiToday(params?: { limit?: number }) {
    return api.post<{ recommendations: AIRecommendation[] }>('/recipes/ai/today', null, { params });
  },

  sources() {
    return api.get<RecipeSource>('/recipes/sources');
  },

  consumePreview(id: number) {
    return api.get<ConsumePreview>(`/recipes/${id}/consume-preview`);
  },

  cook(
    id: number,
    data: { consume_items: { item_id: number; quantity: number }[]; notes?: string | null },
  ) {
    return api.post<CookResponse>(`/recipes/${id}/cook`, data);
  },
};
