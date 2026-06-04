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
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { recipesApi } from '../api/recipes';
import type { RecipeSummary } from '../types';
import { neoCard, neoFilterChip, colors, spacing, radius, shadowXl } from '../theme';
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
  const [isSearchExpanded, setIsSearchExpanded] = useState(false);
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
    if (!isSearchExpanded) {
      setIsSearchExpanded(true);
      setTimeout(() => searchInputRef.current?.focus(), 100);
      return;
    }

    const trimmed = searchDraft.trim();
    if (trimmed) {
      currentSearchTerm.current = trimmed;
      setLoading(true);
      fetchRecipes();
    } else {
      currentSearchTerm.current = '';
      setIsSearchExpanded(false);
      setSearchDraft('');
      Keyboard.dismiss();
      setLoading(true);
      fetchRecipes();
    }
  };

  const renderItem = ({ item }: { item: RecipeSummary }) => (
    <TouchableOpacity
      style={styles.item}
      activeOpacity={0.85}
      onPress={() => navigation.navigate('RecipeDetail', { id: item.id })}
    >
      <View style={styles.itemHeader}>
        <Text style={styles.itemName} numberOfLines={1}>{item.title}</Text>
        <View style={styles.badges}>
          {item.is_favorite && <Ionicons name="heart" size={16} color="#ef4444" />}
          {item.has_been_cooked && <Ionicons name="checkmark-circle" size={16} color="#10b981" />}
        </View>
      </View>
      <View style={styles.itemMeta}>
        <Text style={styles.metaText}>{item.category || '未分类'}</Text>
        <Text style={styles.metaDivider}>·</Text>
        <Text style={styles.metaText}>{SOURCE_LABELS[item.source_type] || item.source_type}</Text>
        {item.difficulty && (
          <>
            <Text style={styles.metaDivider}>·</Text>
            <Text style={styles.metaText}>{DIFFICULTY_LABELS[item.difficulty] || item.difficulty}</Text>
          </>
        )}
        {item.cook_time_minutes && (
          <>
            <Text style={styles.metaDivider}>·</Text>
            <Text style={styles.metaText}>{item.cook_time_minutes} 分钟</Text>
          </>
        )}
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <View style={styles.searchRow}>
        {isSearchExpanded ? (
          <>
            <View style={styles.searchInputWrapper}>
              <TextInput
                ref={searchInputRef}
                style={styles.searchInput}
                value={searchDraft}
                onChangeText={setSearchDraft}
                placeholder="搜索菜谱..."
                placeholderTextColor={colors.textMuted}
                returnKeyType="search"
                onSubmitEditing={handleSearch}
              />
            </View>
            <TouchableOpacity style={styles.searchBtn} activeOpacity={0.85} onPress={handleSearch}>
              <Ionicons name="search" size={20} color="#ffffff" />
            </TouchableOpacity>
          </>
        ) : (
          <TouchableOpacity style={[styles.searchBtn, { marginLeft: 'auto' }]} activeOpacity={0.85} onPress={handleSearch}>
            <Ionicons name="search" size={20} color="#ffffff" />
          </TouchableOpacity>
        )}
      </View>

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
          contentContainerStyle={recipes.length === 0 ? styles.emptyContainer : { paddingBottom: 80 }}
        />
      )}

      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('RecipeRecommendations')}
      >
        <Ionicons name="bulb" size={26} color="#ffffff" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.fabExplore}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('RecipeExplore')}
      >
        <Ionicons name="sparkles" size={26} color="#ffffff" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.fabAdd}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('RecipeEdit', {})}
      >
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  searchRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg - 2,
    paddingTop: spacing.md,
    gap: spacing.sm,
    backgroundColor: colors.bg,
  },
  searchInputWrapper: {
    flex: 1,
    backgroundColor: colors.inputBg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.inputBorder,
    paddingHorizontal: spacing.md,
    justifyContent: 'center',
  },
  searchInput: { fontSize: 15, color: colors.textPrimary, paddingVertical: spacing.md - 4 },
  searchBtn: {
    backgroundColor: colors.accent,
    width: 44,
    height: 44,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
  },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.md,
    gap: spacing.sm - 2,
    backgroundColor: colors.bg,
  },
  filterChipText: { fontSize: 13, color: colors.textSecondary },
  filterChipTextActive: { color: colors.white, fontWeight: '600' },
  item: {
    ...neoCard,
    marginHorizontal: spacing.lg - 2,
    marginTop: spacing.md,
    padding: spacing.lg,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, flex: 1 },
  badges: { flexDirection: 'row', gap: 4, marginLeft: spacing.sm },
  itemMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs + 1,
    flexWrap: 'wrap',
  },
  metaText: { fontSize: 13, color: colors.textSecondary },
  metaDivider: { fontSize: 13, color: colors.textMuted, marginHorizontal: 4 },
  empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center' },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  fab: {
    position: 'absolute',
    right: spacing.xl,
    bottom: spacing.xl + 64,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#f59e0b',
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowXl,
  },
  fabAdd: {
    position: 'absolute',
    right: spacing.xl,
    bottom: spacing.xl,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.accent,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowXl,
  },
  fabText: { fontSize: 28, color: colors.white, lineHeight: 30, marginTop: -1 },
  fabExplore: {
    position: 'absolute',
    right: spacing.xl,
    bottom: spacing.xl + 128,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#7c3aed',
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowXl,
  },

});
