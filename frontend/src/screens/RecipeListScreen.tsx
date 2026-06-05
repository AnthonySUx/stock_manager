import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  Keyboard,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { recipesApi } from '../api/recipes';
import type { RecipeSummary } from '../types';
import { neoCard, neoFilterChip, colors, spacing, radius, shadowXl, neuIn, neuOut } from '../theme';
import { Ionicons } from '@expo/vector-icons';

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

export default function RecipeListScreen({ navigation }: Props) {
  const [recipes, setRecipes] = useState<RecipeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchDraft, setSearchDraft] = useState('');
  const searchInputRef = useRef<TextInput>(null);
  const currentSearchTerm = useRef('');
  const [filterSource, setFilterSource] = useState<string | null>(null);

  const fetchRecipes = useCallback(async () => {
    try {
      const params: any = {};
      if (filterSource) params.source_type = filterSource;
      if (currentSearchTerm.current.trim()) params.query = currentSearchTerm.current.trim();
      const res = await recipesApi.list(params);
      setRecipes(res.data);
    } catch {
      Alert.alert('错误', '加载菜谱失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filterSource]);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      fetchRecipes();
    }, [fetchRecipes])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchRecipes();
  };

  const handleSearch = () => {
    const trimmed = searchDraft.trim();
    currentSearchTerm.current = trimmed;
    setLoading(true);
    fetchRecipes();
    Keyboard.dismiss();
  };

  const getMatchLevel = (item: RecipeSummary): { label: string; level: 'high' | 'medium' | 'low' } | null => {
    // Determine match level based on recipe data
    // For now use is_favorite or has_been_cooked as heuristic
    if (item.is_favorite) return { label: '90% 匹配', level: 'high' };
    if (item.has_been_cooked) return { label: '70% 匹配', level: 'medium' };
    return null;
  };

  const renderItem = ({ item }: { item: RecipeSummary }) => {
    const match = getMatchLevel(item);
    return (
      <TouchableOpacity
        style={styles.recipeCard}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('RecipeDetail', { id: item.id })}
      >
        {/* Top row: match badge + favorite */}
        <View style={styles.recipeCardTop}>
          {match ? (
            <View style={[styles.matchBadge, match.level === 'high' ? styles.matchHigh : styles.matchMedium]}>
              <View style={[styles.matchDot, match.level === 'high' ? styles.dotHigh : styles.dotMedium]} />
              <Text style={[styles.matchText, match.level === 'high' ? styles.matchTextHigh : styles.matchTextMedium]}>
                {match.label}
              </Text>
            </View>
          ) : (
            <View />
          )}
          <View style={styles.favBtnWrap}>
            <Ionicons
              name={item.is_favorite ? 'heart' : 'heart-outline'}
              size={16}
              color={item.is_favorite ? '#FF4757' : colors.textMuted}
            />
          </View>
        </View>

        {/* Title */}
        <Text style={styles.recipeTitle} numberOfLines={1}>{item.title}</Text>

        {/* Tags */}
        <View style={styles.recipeTags}>
          <View style={styles.tag}>
            <Ionicons name="home" size={11} color={colors.textMuted} style={{ marginRight: 3 }} />
            <Text style={styles.tagText}>{item.category || '家常菜'}</Text>
          </View>
          {item.difficulty && (
            <View style={styles.tag}>
              <Ionicons name="flame" size={11} color={colors.textMuted} style={{ marginRight: 3 }} />
              <Text style={styles.tagText}>{DIFFICULTY_LABELS[item.difficulty] || item.difficulty}</Text>
            </View>
          )}
          {item.cook_time_minutes && (
            <View style={styles.tag}>
              <Ionicons name="time" size={11} color={colors.textMuted} style={{ marginRight: 3 }} />
              <Text style={styles.tagText}>{item.cook_time_minutes} 分钟</Text>
            </View>
          )}
        </View>

        {/* Bottom row: cook button */}
        <View style={styles.recipeActions}>
          <Text style={styles.recipeSource}>
            <Ionicons name="bookmark" size={11} color={colors.textMuted} style={{ marginRight: 4 }} />
            {' '}{SOURCE_LABELS[item.source_type] || item.source_type}
          </Text>
          <TouchableOpacity
            style={styles.cookBtn}
            activeOpacity={0.85}
            onPress={() => {
              if (item.has_been_cooked) {
                navigation.navigate('RecipeDetail', { id: item.id });
              } else {
                navigation.navigate('RecipeCook', { id: item.id });
              }
            }}
          >
            <Ionicons name="flame" size={13} color={colors.accent} style={{ marginRight: 4 }} />
            <Text style={styles.cookBtnText}>
              {item.has_been_cooked ? '查看详情' : '去烹饪'}
            </Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  };

  const insets = useSafeAreaInsets();

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={[styles.headerRow, { paddingTop: insets.top + spacing.sm }]}>
        <Text style={styles.screenTitle}>智能菜谱</Text>
      </View>

      {/* Search bar - always visible capsule */}
      <View style={styles.searchRow}>
        <View style={styles.searchBar}>
          <Ionicons name="search" size={16} color={colors.textMuted} style={{ marginRight: 8 }} />
          <TextInput
            ref={searchInputRef}
            style={styles.searchInput}
            value={searchDraft}
            onChangeText={setSearchDraft}
            placeholder="自然语言探索：我想吃点清淡的..."
            placeholderTextColor={colors.textMuted}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
          />
        </View>
        <TouchableOpacity style={styles.searchBtn} activeOpacity={0.85} onPress={handleSearch}>
          <Ionicons name="search" size={18} color="#ffffff" />
        </TouchableOpacity>
      </View>

      {/* Section title */}
      <Text style={styles.sectionTitle}>基于库存今日推荐</Text>

      {/* Filter chips */}
      <View style={styles.filterRow}>
        {[
          { label: '全部', value: null },
          { label: '我的', value: 'user' },
          { label: 'HowToCook', value: 'howtocook' },
          { label: 'AI 建议', value: 'ai_saved' },
        ].map((f) => (
          <TouchableOpacity
            key={String(f.value)}
            style={neoFilterChip(filterSource === f.value)}
            activeOpacity={0.7}
            onPress={() => setFilterSource(f.value)}
          >
            <Text
              style={[
                styles.filterChipText,
                filterSource === f.value && styles.filterChipTextActive,
              ]}
            >
              {f.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
      ) : (
        <FlatList
          data={recipes}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={colors.textMuted}
              colors={[colors.accent]}
            />
          }
          ListEmptyComponent={<Text style={styles.empty}>暂无菜谱</Text>}
          contentContainerStyle={recipes.length === 0 ? styles.emptyContainer : { paddingBottom: 120 }}
        />
      )}

      {/* FABs - consolidated to two main ones */}
      <TouchableOpacity
        style={styles.fabExplore}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('RecipeExplore')}
      >
        <Ionicons name="sparkles" size={24} color="#ffffff" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.fabAdd}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('RecipeRecommendations')}
      >
        <Ionicons name="bulb" size={24} color="#ffffff" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.sm,
    backgroundColor: colors.bg,
  },
  screenTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  // Search
  searchRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.xl,
    gap: spacing.sm,
    marginBottom: spacing.xl,
  },
  searchBar: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.inputBg,
    shadowColor: colors.shadowInset,
    shadowOffset: { width: -2, height: -2 },
    shadowOpacity: 0.5,
    shadowRadius: 3,
    elevation: 1,
  },
  searchInput: {
    flex: 1,
    fontSize: 14,
    color: colors.textPrimary,
    paddingVertical: 0,
  },
  searchBtn: {
    backgroundColor: colors.accent,
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  // Section
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.textPrimary,
    marginHorizontal: spacing.xl,
    marginBottom: spacing.md,
  },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.xl - 2,
    paddingBottom: spacing.md,
    gap: spacing.sm - 2,
  },
  filterChipText: { fontSize: 13, color: colors.textSecondary },
  filterChipTextActive: { color: colors.white, fontWeight: '600' },
  // Recipe card
  recipeCard: {
    marginHorizontal: spacing.xl,
    marginBottom: spacing.xl,
    padding: spacing.xl,
    borderRadius: 30,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.36,
    shadowRadius: 12,
    elevation: 4,
  },
  recipeCardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  matchBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: 16,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowInset,
    shadowOffset: { width: -2, height: -2 },
    shadowOpacity: 0.4,
    shadowRadius: 3,
    elevation: 1,
  },
  matchHigh: {},
  matchMedium: {},
  matchDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  dotHigh: {
    backgroundColor: colors.success,
    shadowColor: colors.success,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  dotMedium: {
    backgroundColor: colors.warning,
    shadowColor: colors.warning,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  matchText: { fontSize: 11, fontWeight: '700' },
  matchTextHigh: { color: colors.accent },
  matchTextMedium: { color: colors.textMuted },
  favBtnWrap: {
    width: 34,
    height: 34,
    borderRadius: 17,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 3, height: 3 },
    shadowOpacity: 0.2,
    shadowRadius: 5,
    elevation: 3,
  },
  recipeTitle: { fontSize: 17, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.md },
  recipeTags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  tag: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md - 2,
    paddingVertical: spacing.xs + 1,
    borderRadius: 14,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowInset,
    shadowOffset: { width: -1, height: -1 },
    shadowOpacity: 0.3,
    shadowRadius: 2,
    elevation: 1,
  },
  tagText: { fontSize: 11, fontWeight: '600', color: colors.textSecondary },
  recipeActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  recipeSource: { fontSize: 12, color: colors.textMuted },
  cookBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: 22,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.36,
    shadowRadius: 8,
    elevation: 4,
  },
  cookBtnText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.accent,
  },
  empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center' },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  // FABs
  fabExplore: {
    position: 'absolute',
    right: spacing.xl,
    bottom: spacing.xl + 74,
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: '#7c3aed',
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 12,
    elevation: 7,
  },
  fabAdd: {
    position: 'absolute',
    right: spacing.xl,
    bottom: spacing.xl,
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: colors.accent,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 12,
    elevation: 7,
  },
});
