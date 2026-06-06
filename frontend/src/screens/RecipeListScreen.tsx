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
import { colors, spacing, radius } from '../theme';
import { Ionicons } from '@expo/vector-icons';
import { PressableScale, NeuOut, NeuIn, NeuIconBtn } from '../components/NeoComponents';

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
        let iconName: keyof typeof Ionicons.glyphMap = 'restaurant';
        const cat = (item.category || '').toLowerCase();
        if (cat.includes('汤')) iconName = 'water';
        else if (cat.includes('炒') || cat.includes('热菜')) iconName = 'flame';
        else if (cat.includes('凉菜')) iconName = 'snow';
        else if (cat.includes('主食') || cat.includes('饭') || cat.includes('面')) iconName = 'cafe';
        else if (cat.includes('甜品') || cat.includes('甜点')) iconName = 'ice-cream';
        else if (cat.includes('海鲜')) iconName = 'fish';
        else if (cat.includes('沙拉')) iconName = 'leaf';
        return (
            <PressableScale
                onPress={() => navigation.navigate('RecipeDetail', { id: item.id })}
                scaleIn={0.97}
            >
                <NeuOut borderRadius={36} depth="sm" style={styles.recipeCard}>
                    <View style={styles.recipeRow}>
                        {/* Left: inset icon circle */}
                        <NeuIn borderRadius={50} depth="sm" style={styles.recipeIconCircle}>
                            <Ionicons name={iconName} size={22} color={colors.accent} />
                        </NeuIn>

                        {/* Center: recipe info */}
                        <View style={styles.recipeInfo}>
                            <Text style={styles.recipeName} numberOfLines={1}>{item.title}</Text>
                            <Text style={styles.recipeDesc} numberOfLines={1}>
                                {item.category || '家常菜'}
                                {item.difficulty ? ` · ${DIFFICULTY_LABELS[item.difficulty] || item.difficulty}` : ''}
                                {item.cook_time_minutes ? ` · ${item.cook_time_minutes}分钟` : ''}
                            </Text>
                        </View>

                        {/* Right: match badge + favorite */}
                        <View style={styles.recipeRight}>
                            {match && (
                                <View style={[styles.matchBadge, match.level === 'high' ? styles.matchHighBg : styles.matchMediumBg]}>
                                    <Text style={[styles.matchNum, match.level === 'high' ? styles.matchNumHigh : styles.matchNumMed]}>
                                        {match.label}
                                    </Text>
                                </View>
                            )}
                            <Ionicons
                                name={item.is_favorite ? 'heart' : 'heart-outline'}
                                size={18}
                                color={item.is_favorite ? '#FF4757' : colors.textMuted}
                            />
                        </View>
                    </View>

                    {/* Bottom row: source + cook */}
                    <View style={styles.recipeActions}>
                        <Text style={styles.recipeSource}>
                            <Ionicons name="bookmark" size={11} color={colors.textMuted} />
                            {' '}{SOURCE_LABELS[item.source_type] || item.source_type}
                        </Text>
                        <TouchableOpacity
                            onPress={() => {
                                if (item.has_been_cooked) {
                                    navigation.navigate('RecipeDetail', { id: item.id });
                                } else {
                                    navigation.navigate('RecipeCook', { id: item.id });
                                }
                            }}
                            activeOpacity={0.7}
                        >
                            <View style={styles.cookBtn}>
                                <Ionicons name="flame" size={13} color={colors.accent} style={{ marginRight: 4 }} />
                                <Text style={styles.cookBtnText}>
                                    {item.has_been_cooked ? '查看详情' : '去烹饪'}
                                </Text>
                            </View>
                        </TouchableOpacity>
                    </View>
                </NeuOut>
            </PressableScale>
        );
    };

    const insets = useSafeAreaInsets();

    return (
        <View style={styles.container}>
            {/* Header */}
            <View style={[styles.headerArea, { paddingTop: insets.top + spacing.sm }]}>
                <View style={styles.headerTopRow}>
                    <Text style={styles.screenTitle}>智能菜谱</Text>
                    <PressableScale
                        onPress={() => navigation.navigate('RecipeRecommendations')}
                        scaleIn={0.92}
                    >
                        <NeuIconBtn size={52} backgroundColor={colors.accentBg}>
                            <Ionicons name="bulb-outline" size={27} color={colors.accent} />
                        </NeuIconBtn>
                    </PressableScale>
                </View>
            </View>

            {/* Search bar — NeuIn background */}
            <View style={[styles.searchBar, styles.searchBarLayer]}>
                <NeuIn borderRadius={27} depth="md" style={StyleSheet.absoluteFill} />
                <View style={styles.searchRow}>
                    <Ionicons name="search" size={18} color={colors.textMuted} style={styles.searchIcon} />
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
                    <PressableScale onPress={handleSearch} scaleIn={0.92}>
                        <View style={styles.searchBtn}>
                            <Ionicons name="search" size={18} color="#ffffff" />
                        </View>
                    </PressableScale>
                </View>
            </View>

            {/* Section title */}
            <Text style={styles.sectionTitle}>基于库存今日推荐</Text>

            {/* Filter chips — NeuOut / NeuIn toggle */}
            <View style={styles.filterRow}>
                {[
                    { label: '全部', value: null },
                    { label: '我的', value: 'user' },
                    { label: 'HowToCook', value: 'howtocook' },
                    { label: 'AI 建议', value: 'ai_saved' },
                ].map((f) => {
                    const isActive = filterSource === f.value;
                    return (
                        <TouchableOpacity
                            key={String(f.value)}
                            activeOpacity={0.7}
                            onPress={() => setFilterSource(f.value)}
                        >
                            {isActive ? (
                                <NeuIn borderRadius={18} depth="sm" style={styles.filterChip}>
                                    <Text style={styles.filterChipTextActive}>{f.label}</Text>
                                </NeuIn>
                            ) : (
                                <NeuOut borderRadius={18} depth="sm" style={styles.filterChip}>
                                    <Text style={styles.filterChipText}>{f.label}</Text>
                                </NeuOut>
                            )}
                        </TouchableOpacity>
                    );
                })}
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

        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.bg },
    loader: { flex: 1, justifyContent: 'center' },
    headerArea: {
        paddingHorizontal: spacing.xl,
        paddingBottom: spacing.sm,
        backgroundColor: colors.bg,
    },
    headerTopRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: spacing.xs,
    },
    screenTitle: {
        fontSize: 28,
        fontWeight: '700',
        color: colors.textPrimary,
    },
    // Search bar
    searchBar: {
        marginHorizontal: spacing.xl,
        marginTop: spacing.md,
        marginBottom: spacing.xl,
        height: 54,
        justifyContent: 'center',
    },
    searchBarLayer: {
        position: 'relative',
    },
    searchRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.xl,
        flex: 1,
        gap: spacing.sm,
    },
    searchIcon: {
        marginRight: 10,
    },
    searchInput: {
        flex: 1,
        fontSize: 15,
        color: colors.textPrimary,
        paddingVertical: 0,
    },
    searchBtn: {
        backgroundColor: colors.accent,
        width: 40,
        height: 40,
        borderRadius: 20,
        alignItems: 'center',
        justifyContent: 'center',
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
    filterChip: {
        paddingHorizontal: 14,
        paddingVertical: 6,
    },
    filterChipText: { fontSize: 13, color: colors.textSecondary, fontWeight: '500' },
    filterChipTextActive: { fontSize: 13, color: colors.accent, fontWeight: '600' },
    // Recipe card
    recipeCard: {
        marginHorizontal: spacing.xl,
        marginBottom: spacing.md,
        paddingVertical: spacing.xxl,
        paddingHorizontal: spacing.xl,
    },
    recipeRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    recipeIconCircle: {
        width: 52,
        height: 52,
        borderRadius: 26,
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: spacing.lg,
    },
    recipeInfo: { flex: 1, marginRight: spacing.sm },
    recipeName: { fontSize: 15, fontWeight: '600', color: colors.textPrimary, marginBottom: 2 },
    recipeDesc: { fontSize: 12, color: colors.textMuted },
    recipeRight: { alignItems: 'flex-end', gap: 6 },
    matchBadge: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 10,
    },
    matchHighBg: { backgroundColor: 'rgba(46, 213, 115, 0.15)' },
    matchMediumBg: { backgroundColor: 'rgba(255, 165, 2, 0.15)' },
    matchNum: { fontSize: 11, fontWeight: '700' },
    matchNumHigh: { color: colors.success },
    matchNumMed: { color: colors.warning },
    // Actions row
    recipeActions: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginTop: spacing.md,
        paddingTop: spacing.md,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.textMuted + '20',
    },
    recipeSource: { fontSize: 12, color: colors.textMuted },
    cookBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.sm + 2,
        backgroundColor: colors.accentBg,
        borderRadius: 22,
        shadowColor: colors.shadowInset,
        shadowOffset: { width: -1, height: -1 },
        shadowOpacity: 0.3,
        shadowRadius: 3,
        elevation: 1,
    },
    cookBtnText: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.accent,
    },
    empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center', marginTop: 40 },
    emptyContainer: { flex: 1, justifyContent: 'center' },
});
