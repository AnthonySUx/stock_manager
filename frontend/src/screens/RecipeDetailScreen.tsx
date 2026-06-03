import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { recipesApi } from '../api/recipes';
import type { RecipeResponse } from '../types';
import { neoCard, colors, spacing, radius, shadowMd } from '../theme';
import { Ionicons, Feather } from '@expo/vector-icons';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const SOURCE_LABELS: Record<string, string> = {
  howtocook: 'HowToCook',
  user: '我的',
  ai_saved: 'AI 建议',
};

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
};

export default function RecipeDetailScreen({ navigation }: Props) {
  const route = useRoute<any>();
  const { id } = route.params;
  const [recipe, setRecipe] = useState<RecipeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchRecipe = useCallback(async () => {
    try {
      const res = await recipesApi.get(id);
      setRecipe(res.data);
    } catch {
      Alert.alert('错误', '未找到菜谱');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      fetchRecipe();
    }, [fetchRecipe])
  );

  const handleToggleFavorite = async () => {
    if (!recipe) return;
    try {
      if (recipe.is_favorite) {
        await recipesApi.removeFavorite(recipe.id);
      } else {
        await recipesApi.addFavorite(recipe.id);
      }
      setRecipe({ ...recipe, is_favorite: !recipe.is_favorite });
    } catch {
      Alert.alert('错误', '操作失败');
    }
  };

  const handleFork = async () => {
    if (!recipe) return;
    try {
      const res = await recipesApi.fork(recipe.id);
      Alert.alert('已复制', '已创建可编辑副本', [
        { text: '确定', onPress: () => navigation.replace('RecipeDetail', { id: res.data.id }) },
      ]);
    } catch {
      Alert.alert('错误', '复制失败');
    }
  };

  const handleDelete = () => {
    if (!recipe) return;
    Alert.alert('删除菜谱', '确定要删除此菜谱吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await recipesApi.delete(recipe.id);
            Alert.alert('已删除', '菜谱已删除', [
              { text: '确定', onPress: () => navigation.goBack() },
            ]);
          } catch {
            Alert.alert('错误', '删除失败');
          }
        },
      },
    ]);
  };

  const handleCook = () => {
    if (!recipe) return;
    navigation.navigate('RecipeCook', { id: recipe.id, title: recipe.title });
  };

  if (loading) {
    return <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />;
  }

  if (!recipe) return null;

  return (
    <ScrollView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerTop}>
          <Text style={styles.title}>{recipe.title}</Text>
          <TouchableOpacity onPress={handleToggleFavorite} activeOpacity={0.7}>
            <Ionicons
              name={recipe.is_favorite ? 'heart' : 'heart-outline'}
              size={28}
              color={recipe.is_favorite ? '#ef4444' : colors.textMuted}
            />
          </TouchableOpacity>
        </View>
        <View style={styles.metaRow}>
          <View style={styles.metaChip}>
            <Text style={styles.metaChipText}>{SOURCE_LABELS[recipe.source_type] || recipe.source_type}</Text>
          </View>
          {recipe.category && (
            <View style={styles.metaChip}>
              <Text style={styles.metaChipText}>{recipe.category}</Text>
            </View>
          )}
          {recipe.difficulty && (
            <View style={styles.metaChip}>
              <Text style={styles.metaChipText}>{DIFFICULTY_LABELS[recipe.difficulty] || recipe.difficulty}</Text>
            </View>
          )}
        </View>
      </View>

      {/* Description */}
      {recipe.description && (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>描述</Text>
          <Text style={styles.description}>{recipe.description}</Text>
        </View>
      )}

      {/* Info */}
      <View style={styles.card}>
        <View style={styles.infoRow}>
          <View style={styles.infoItem}>
            <Ionicons name="time-outline" size={18} color={colors.textSecondary} />
            <Text style={styles.infoText}>
              {recipe.cook_time_minutes ? `${recipe.cook_time_minutes} 分钟` : '未指定'}
            </Text>
          </View>
          <View style={styles.infoItem}>
            <Ionicons name="people-outline" size={18} color={colors.textSecondary} />
            <Text style={styles.infoText}>{recipe.servings || '未指定'}</Text>
          </View>
        </View>
      </View>

      {/* Ingredients */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>食材 ({recipe.ingredients.length})</Text>
        {recipe.ingredients.map((ing, idx) => (
          <View key={idx} style={styles.ingredientRow}>
            <View style={styles.bullet} />
            <Text style={styles.ingredientName}>{ing.ingredient_name}</Text>
            {(ing.quantity || ing.unit) && (
              <Text style={styles.ingredientQty}>
                {ing.quantity || ''} {ing.unit || ''}
              </Text>
            )}
          </View>
        ))}
      </View>

      {/* Steps */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>步骤 ({recipe.steps.length})</Text>
        {recipe.steps.map((step, idx) => (
          <View key={idx} style={styles.stepRow}>
            <View style={styles.stepNumber}>
              <Text style={styles.stepNumberText}>{step.step_number}</Text>
            </View>
            <Text style={styles.stepInstruction}>{step.instruction}</Text>
          </View>
        ))}
      </View>

      {/* Source Attribution */}
      {recipe.source_url && (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>来源</Text>
          <Text style={styles.sourceText}>{recipe.source_name}</Text>
          {recipe.license_name && <Text style={styles.sourceText}>许可: {recipe.license_name}</Text>}
        </View>
      )}

      {/* Actions */}
      <View style={styles.actions}>
        {!recipe.is_user_created ? (
          <TouchableOpacity
            style={styles.forkBtn}
            activeOpacity={0.85}
            onPress={handleFork}
          >
            <Feather name="copy" size={18} color="#ffffff" />
            <Text style={styles.actionBtnText}>复制并编辑</Text>
          </TouchableOpacity>
        ) : (
          <>
            <TouchableOpacity
              style={styles.editBtn}
              activeOpacity={0.85}
              onPress={() => navigation.navigate('RecipeEdit', { id: recipe.id })}
            >
              <Feather name="edit-2" size={18} color="#ffffff" />
              <Text style={styles.actionBtnText}>编辑</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.deleteBtn}
              activeOpacity={0.85}
              onPress={handleDelete}
            >
              <Feather name="trash-2" size={18} color="#ffffff" />
              <Text style={styles.actionBtnText}>删除</Text>
            </TouchableOpacity>
          </>
        )}
      </View>

      {/* Cook Button */}
      <TouchableOpacity style={styles.cookBtn} activeOpacity={0.85} onPress={handleCook}>
        <Feather name="check-circle" size={20} color="#ffffff" />
        <Text style={styles.cookBtnText}>烹饪此菜谱</Text>
      </TouchableOpacity>

      <View style={styles.bottomSpacer} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  header: {
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: { fontSize: 24, fontWeight: '700', color: colors.textPrimary, flex: 1, marginRight: spacing.sm },
  metaRow: { flexDirection: 'row', marginTop: spacing.md, gap: spacing.sm, flexWrap: 'wrap' },
  metaChip: {
    backgroundColor: colors.chipBg,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 0.5,
    borderColor: colors.surfaceBorder,
  },
  metaChipText: { fontSize: 12, color: colors.textSecondary },
  card: {
    ...neoCard,
    margin: spacing.lg,
    marginBottom: 0,
    padding: spacing.lg,
  },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.md },
  description: { fontSize: 15, color: colors.textSecondary, lineHeight: 22 },
  infoRow: { flexDirection: 'row', gap: spacing.xl },
  infoItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  infoText: { fontSize: 14, color: colors.textSecondary },
  ingredientRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  bullet: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.accent,
    marginRight: spacing.sm,
  },
  ingredientName: { fontSize: 15, color: colors.textPrimary, flex: 1 },
  ingredientQty: { fontSize: 14, color: colors.textSecondary, marginLeft: spacing.sm },
  stepRow: {
    flexDirection: 'row',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  stepNumber: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.accentBg,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
    marginTop: 2,
  },
  stepNumberText: { fontSize: 13, fontWeight: '700', color: colors.accent },
  stepInstruction: { fontSize: 15, color: colors.textPrimary, flex: 1, lineHeight: 22 },
  sourceText: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.xs },
  actions: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    gap: spacing.lg,
  },
  forkBtn: {
    backgroundColor: '#3b82f6',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  editBtn: {
    backgroundColor: '#3b82f6',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  deleteBtn: {
    backgroundColor: '#ef4444',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  actionBtnText: { color: colors.white, fontSize: 15, fontWeight: '600' },
  cookBtn: {
    backgroundColor: '#10b981',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    paddingVertical: spacing.md + 2,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  cookBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
  bottomSpacer: { height: 40 },
});
