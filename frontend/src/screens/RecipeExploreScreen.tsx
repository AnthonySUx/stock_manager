import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { recipesApi } from '../api/recipes';
import type {
  ExploreIdea,
  ExploreMode,
  ExploreRequest,
  ExploreResponse,
  ExploreStructuredPreferences,
} from '../types';
import { neoCard, colors, spacing, radius, shadowMd } from '../theme';
import { PressableScale } from '../components/NeoComponents';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const MODE_OPTIONS: { label: string; value: ExploreMode; icon: keyof typeof Ionicons.glyphMap }[] = [
  { label: '结构化偏好', value: 'structured', icon: 'options' },
  { label: '自然语言', value: 'natural_language', icon: 'chatbubbles' },
];

export default function RecipeExploreScreen({ navigation }: Props) {
  const [mode, setMode] = useState<ExploreMode>('structured');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExploreResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Structured
  const [cuisine, setCuisine] = useState('');
  const [flavor, setFlavor] = useState('');
  const [texture, setTexture] = useState('');
  const [mainIngredient, setMainIngredient] = useState('');
  const [avoidIngredients, setAvoidIngredients] = useState('');
  const [mealType, setMealType] = useState('');
  const [maxCookTime, setMaxCookTime] = useState('');

  // Natural language
  const [prompt, setPrompt] = useState('');

  const buildStructured = (): ExploreStructuredPreferences | null => {
    if (!cuisine && !flavor && !texture && !mainIngredient && !avoidIngredients && !mealType && !maxCookTime) {
      return null;
    }
    return {
      cuisine: cuisine || null,
      flavor: flavor || null,
      texture: texture || null,
      main_ingredient: mainIngredient || null,
      avoid_ingredients: avoidIngredients
        ? avoidIngredients.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
        : null,
      meal_type: mealType || null,
      max_cook_time_minutes: maxCookTime ? parseInt(maxCookTime, 10) || null : null,
    };
  };

  const handleExplore = async () => {
    setError(null);
    setResult(null);

    const request: ExploreRequest =
      mode === 'structured'
        ? { mode: 'structured', structured: buildStructured(), natural_language: null }
        : { mode: 'natural_language', structured: null, natural_language: prompt.trim() || null };

    setLoading(true);
    try {
      const res = await recipesApi.explore(request);
      setResult(res.data);
    } catch {
      setError('探索失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const handleIdeaPress = (idea: ExploreIdea) => {
    if (idea.recipe_id) {
      navigation.navigate('RecipeDetail', { id: idea.recipe_id });
    }
  };

  const handleExpandToDraft = (idea: ExploreIdea) => {
    navigation.navigate('RecipeEdit', {
      title: idea.title,
      description: idea.description || '',
    });
  };

  const renderWarnings = () => {
    if (!result || result.warnings.length === 0) return null;
    return (
      <View style={styles.warningsContainer}>
        {result.warnings.map((w, idx) => (
          <View key={idx} style={styles.warningRow}>
            <Ionicons name="warning" size={16} color="#f59e0b" />
            <Text style={styles.warningText}>{w}</Text>
          </View>
        ))}
      </View>
    );
  };

  const renderIdea = (idea: ExploreIdea, idx: number) => {
    const matched = idea.matched_ingredients ?? [];
    const expiring = idea.expiring_ingredients ?? [];
    const missing = idea.missing_ingredients ?? [];

    return (
      <PressableScale
        key={idx}
        scaleIn={0.97}
        style={styles.ideaCard}
        onPress={() => handleIdeaPress(idea)}
      >
        <Text style={styles.ideaTitle}>{idea.title}</Text>

        {idea.description ? (
          <Text style={styles.ideaDescription}>{idea.description}</Text>
        ) : null}

        {/* Info tags */}
        <View style={styles.ideaTags}>
          {idea.cuisine ? (
            <View style={[styles.tag, styles.tagCuisine]}>
              <Text style={styles.tagText}>{idea.cuisine}</Text>
            </View>
          ) : null}
          {idea.flavor ? (
            <View style={[styles.tag, styles.tagFlavor]}>
              <Text style={styles.tagText}>{idea.flavor}</Text>
            </View>
          ) : null}
          {idea.texture ? (
            <View style={[styles.tag, styles.tagTexture]}>
              <Text style={styles.tagText}>{idea.texture}</Text>
            </View>
          ) : null}
        </View>

        {/* Ingredients */}
        {matched.length > 0 && (
          <Text style={styles.ingredientLine}>
            <Text style={styles.ingredientLabel}>{'✅'} 匹配: </Text>
            {matched.join(', ')}
          </Text>
        )}
        {expiring.length > 0 && (
          <Text style={[styles.ingredientLine, { color: '#f59e0b' }]}>
            <Text style={styles.ingredientLabel}>{'⚠️'} 临期: </Text>
            {expiring.join(', ')}
          </Text>
        )}
        {missing.length > 0 && (
          <Text style={[styles.ingredientLine, { color: colors.textMuted }]}>
            <Text style={styles.ingredientLabel}>{'❌'} 缺: </Text>
            {missing.join(', ')}
          </Text>
        )}

        {/* Action buttons */}
        <View style={styles.ideaActions}>
          {idea.recipe_id && (
            <View style={styles.actionChip}>
              <Ionicons name="eye" size={14} color={colors.accent} />
              <Text style={styles.actionChipText}>查看菜谱</Text>
            </View>
          )}
          {idea.can_expand_to_recipe && (
            <PressableScale
              scaleIn={0.96}
              onPress={() => handleExpandToDraft(idea)}
              style={styles.expandBtn}
            >
              <Ionicons name="add-circle-outline" size={14} color="#7c3aed" />
              <Text style={styles.expandBtnText}>扩展为草稿</Text>
            </PressableScale>
          )}
        </View>
      </PressableScale>
    );
  };

  const renderResults = () => {
    if (loading) {
      return (
        <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
      );
    }
    if (!result) return null;

    const ideas = result.ideas ?? [];

    return (
      <>
        {renderWarnings()}
        {ideas.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="search-outline" size={48} color={colors.textMuted} />
            <Text style={styles.emptyTitle}>暂无想法</Text>
            <Text style={styles.emptyDesc}>当前条件未生成任何菜谱想法，请尝试调整输入。</Text>
          </View>
        ) : (
          <>
            <Text style={styles.resultCount}>共有 {ideas.length} 个想法</Text>
            {ideas.map((idea, idx) => renderIdea(idea, idx))}
          </>
        )}
      </>
    );
  };

  return (
    <ScrollView style={styles.container} keyboardShouldPersistTaps="handled">
      {/* Mode Toggle */}
      <View style={styles.modeRow}>
        {MODE_OPTIONS.map((opt) => (
          <PressableScale
            key={opt.value}
            scaleIn={0.96}
            onPress={() => setMode(opt.value)}
            style={[styles.modeBtn, mode === opt.value && styles.modeBtnActive]}
          >
            <Ionicons
              name={opt.icon}
              size={18}
              color={mode === opt.value ? '#ffffff' : colors.textSecondary}
            />
            <Text style={[styles.modeBtnText, mode === opt.value && styles.modeBtnTextActive]}>
              {opt.label}
            </Text>
          </PressableScale>
        ))}
      </View>

      {/* Structured Form */}
      {mode === 'structured' && (
        <View style={styles.formSection}>
          <Text style={styles.sectionTitle}>偏好设置</Text>
          <TextInput
            style={styles.input}
            placeholder="菜系（如：中式、西式、日式）"
            placeholderTextColor={colors.textMuted}
            value={cuisine}
            onChangeText={setCuisine}
          />
          <TextInput
            style={styles.input}
            placeholder="口味（如：酸甜、麻辣、清淡）"
            placeholderTextColor={colors.textMuted}
            value={flavor}
            onChangeText={setFlavor}
          />
          <TextInput
            style={styles.input}
            placeholder="口感（如：嫩滑、酥脆、软糯）"
            placeholderTextColor={colors.textMuted}
            value={texture}
            onChangeText={setTexture}
          />
          <TextInput
            style={styles.input}
            placeholder="主要食材"
            placeholderTextColor={colors.textMuted}
            value={mainIngredient}
            onChangeText={setMainIngredient}
          />
          <TextInput
            style={styles.input}
            placeholder="避免的食材（逗号分隔）"
            placeholderTextColor={colors.textMuted}
            value={avoidIngredients}
            onChangeText={setAvoidIngredients}
          />
          <TextInput
            style={styles.input}
            placeholder="用餐场景（如：早餐、晚餐、聚会）"
            placeholderTextColor={colors.textMuted}
            value={mealType}
            onChangeText={setMealType}
          />
          <TextInput
            style={styles.input}
            placeholder="最大烹饪时间（分钟）"
            placeholderTextColor={colors.textMuted}
            value={maxCookTime}
            onChangeText={setMaxCookTime}
            keyboardType="number-pad"
          />
        </View>
      )}

      {/* Natural Language Input */}
      {mode === 'natural_language' && (
        <View style={styles.formSection}>
          <Text style={styles.sectionTitle}>描述你的需求</Text>
          <Text style={styles.sectionDesc}>
            用自然语言描述你想吃的菜，例如："用鸡胸肉和西兰花做一道低卡晚餐，清淡口味"
          </Text>
          <TextInput
            style={styles.promptInput}
            placeholder="输入你的描述..."
            placeholderTextColor={colors.textMuted}
            value={prompt}
            onChangeText={setPrompt}
            multiline
            numberOfLines={5}
            textAlignVertical="top"
          />
        </View>
      )}

      {/* Error */}
      {error && (
        <View style={styles.errorBox}>
          <Ionicons name="alert-circle" size={16} color="#ef4444" />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* Submit */}
      <PressableScale
        scaleIn={0.96}
        onPress={handleExplore}
        disabled={loading}
        style={[styles.submitBtn, loading && { opacity: 0.6 }]}
      >
        <Ionicons name="sparkles" size={20} color="#ffffff" />
        <Text style={styles.submitBtnText}>
          {loading ? 'AI 思考中...' : '探索菜谱想法'}
        </Text>
      </PressableScale>

      {/* Results */}
      {renderResults()}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { marginVertical: spacing.xl },

  // Mode toggle
  modeRow: {
    flexDirection: 'row',
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  modeBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.md - 2,
    borderRadius: radius.md,
    backgroundColor: colors.inputBg,
    borderWidth: 1,
    borderColor: colors.inputBorder,
  },
  modeBtnActive: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  modeBtnText: {
    fontSize: 14,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  modeBtnTextActive: {
    color: '#ffffff',
    fontWeight: '700',
  },

  // Form
  formSection: {
    padding: spacing.lg,
    paddingBottom: spacing.sm,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  sectionDesc: {
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: spacing.md,
    lineHeight: 20,
  },
  input: {
    backgroundColor: colors.inputBg,
    borderWidth: 1,
    borderColor: colors.inputBorder,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
    marginTop: spacing.sm,
  },
  promptInput: {
    backgroundColor: colors.inputBg,
    borderWidth: 1,
    borderColor: colors.inputBorder,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    fontSize: 15,
    color: colors.textPrimary,
    minHeight: 120,
    marginTop: spacing.sm,
  },

  // Error
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
    padding: spacing.md,
    backgroundColor: '#fef2f2',
    borderRadius: radius.md,
  },
  errorText: { fontSize: 14, color: '#ef4444', flex: 1 },

  // Submit
  submitBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: '#7c3aed',
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    paddingVertical: spacing.md + 2,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.24)',
    ...shadowMd,
  },
  submitBtnText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },

  // Results
  resultCount: {
    fontSize: 14,
    color: colors.textSecondary,
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
  },

  // Idea card
  ideaCard: {
    ...neoCard,
    marginHorizontal: spacing.lg - 2,
    marginTop: spacing.md,
    padding: spacing.lg,
  },
  ideaTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  ideaDescription: {
    fontSize: 14,
    color: colors.textSecondary,
    marginTop: spacing.xs,
    lineHeight: 20,
  },

  // Tags
  ideaTags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  tag: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.full,
  },
  tagCuisine: { backgroundColor: '#ede9fe' },
  tagFlavor: { backgroundColor: '#fef3c7' },
  tagTexture: { backgroundColor: '#dbeafe' },
  tagText: { fontSize: 12, fontWeight: '600', color: colors.textPrimary },

  // Ingredients
  ingredientLine: {
    fontSize: 13,
    marginTop: spacing.xs,
  },
  ingredientLabel: {
    fontWeight: '600',
    color: colors.textPrimary,
  },

  // Actions
  ideaActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  actionChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.accentBg,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
  },
  actionChipText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.accent,
  },
  expandBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#f3e8ff',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
  },
  expandBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#7c3aed',
  },

  // Warnings
  warningsContainer: {
    marginHorizontal: spacing.lg - 2,
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: '#fffbeb',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: '#fde68a',
  },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  warningText: {
    fontSize: 13,
    color: '#92400e',
    flex: 1,
  },

  // Empty state
  emptyState: {
    alignItems: 'center',
    paddingVertical: spacing.xl * 2,
    marginHorizontal: spacing.lg,
  },
  emptyTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: colors.textPrimary,
    marginTop: spacing.md,
  },
  emptyDesc: {
    fontSize: 14,
    color: colors.textSecondary,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 20,
  },
});
