import React, { useCallback, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    FlatList,
    RefreshControl,
    StyleSheet,
    Text,
    View,
} from 'react-native';
import { useFocusEffect, useRoute } from '@react-navigation/native';

import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import type { Item } from '../types';
import { colors, spacing, radius, status as statusColors } from '../theme';
import { NeuOut, NeuIn, PressableScale } from '../components/NeoComponents';
import { Ionicons } from '@expo/vector-icons';

type Props = {
    navigation: NativeStackNavigationProp<any>;
};

type SummaryMode = 'categories' | 'expiring';

const STATUS_COLORS: Record<string, string> = {
    active: statusColors.active,
    'expiring soon': statusColors.expiringSoon,
    expired: statusColors.expired,
    consumed: colors.textMuted,
};

const getItemIcon = (item: Item): keyof typeof Ionicons.glyphMap => {
    const name = item.name.toLowerCase();
    const cat = (item.category || '').toLowerCase();
    if (name.includes('鸡蛋') || name.includes('蛋')) return 'nutrition';
    if (name.includes('牛奶') || name.includes('奶')) return 'wine';
    if (name.includes('胡萝卜') || name.includes('萝卜') || cat.includes('蔬菜')) return 'leaf';
    if (name.includes('鸡胸') || name.includes('肉') || cat.includes('肉类')) return 'flame';
    if (name.includes('苹果') || name.includes('水果') || cat.includes('水果')) return 'nutrition';
    if (name.includes('面包') || cat.includes('主食')) return 'cafe';
    if (name.includes('饮料') || cat.includes('饮料')) return 'wine';
    return 'cube';
};

const getStatusMeta = (item: Item): { color: string; text: string } => {
    if (item.status === 'expired') return { color: statusColors.expired, text: '已过期' };
    if (item.status === 'expiring soon') return { color: statusColors.expiringSoon, text: '即将过期' };
    if (item.status === 'consumed') return { color: colors.textMuted, text: '已消耗' };
    return { color: statusColors.active, text: '充足' };
};

const formatQuantity = (item: Item) =>
    `${item.quantity_value} ${item.quantity_unit}`;

export default function InventorySummaryScreen({ navigation }: Props) {
    const [allItems, setAllItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const route = useRoute<any>();

    const mode: SummaryMode = route.params?.mode ?? 'categories';
    const screenTitle: string = route.params?.title ?? '库存概览';
    const scene: string = route.params?.scene ?? '全部';

    const fetchItems = useCallback(async () => {
        try {
            const res = await api.get('/items');
            setAllItems(res.data);
        } catch (err: any) {
            Alert.alert('错误', '加载物品失败');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useFocusEffect(
        useCallback(() => {
            setLoading(true);
            fetchItems();
        }, [fetchItems])
    );

    const onRefresh = () => {
        setRefreshing(true);
        fetchItems();
    };

    // Filter by current scene if not "全部"
    const sceneItems = scene === '全部'
        ? allItems
        : allItems.filter((item) => item.location === scene);

    const ItemCard = ({ item }: { item: Item }) => {
        const meta = getStatusMeta(item);
        const iconName = getItemIcon(item);
        return (
            <PressableScale
                onPress={() => navigation.navigate('ItemDetail', { id: item.id })}
                scaleIn={0.97}
            >
                <NeuOut borderRadius={36} depth="sm" style={styles.itemCard}>
                    <View style={styles.itemRow}>
                        <NeuIn borderRadius={50} depth="sm" style={styles.itemIconCircle}>
                            <Ionicons name={iconName} size={22} color={colors.accent} />
                        </NeuIn>
                        <View style={styles.itemInfo}>
                            <Text style={styles.itemName} numberOfLines={1}>{item.name}</Text>
                            <Text style={styles.itemDesc} numberOfLines={1}>
                                {item.location} · {item.category || '未分类'}
                            </Text>
                        </View>
                        <View style={styles.itemStatus}>
                            <Text style={styles.itemQty}>{formatQuantity(item)}</Text>
                            <View style={styles.statusRow}>
                                <View style={[styles.statusDot, { backgroundColor: meta.color }]} />
                                <Text style={styles.statusText}>{meta.text}</Text>
                            </View>
                        </View>
                    </View>
                </NeuOut>
            </PressableScale>
        );
    };

    // ── Categories mode ──
    if (mode === 'categories') {
        const grouped: Record<string, Item[]> = {};
        for (const item of sceneItems) {
            const cat = item.category || '未分类';
            if (!grouped[cat]) grouped[cat] = [];
            grouped[cat].push(item);
        }
        const sortedCategories = Object.keys(grouped).sort();

        const sections: { category: string; items: Item[] }[] = sortedCategories.map(
            (cat) => ({ category: cat, items: grouped[cat] })
        );

        // Flatten into a display list: category header markers + item data
        type ListEntry =
            | { type: 'header'; category: string; count: number }
            | { type: 'item'; item: Item };

        const flatData: ListEntry[] = [];
        for (const section of sections) {
            flatData.push({ type: 'header', category: section.category, count: section.items.length });
            for (const item of section.items) {
                flatData.push({ type: 'item', item });
            }
        }

        return (
            <View style={styles.container}>
                <FlatList
                    ListHeaderComponent={
                        <View style={styles.headerSection} />
                    }
                    data={flatData}
                    keyExtractor={(entry, idx) =>
                        entry.type === 'header' ? `header-${entry.category}` : `item-${entry.item.id}`
                    }
                    renderItem={({ item: entry }) => {
                        if (entry.type === 'header') {
                            return (
                                <View style={styles.categoryHeader}>
                                    <NeuIn borderRadius={16} depth="sm" style={styles.categoryBadge}>
                                        <Ionicons name="folder-outline" size={16} color={colors.accent} />
                                    </NeuIn>
                                    <Text style={styles.categoryTitle}>{entry.category}</Text>
                                    <View style={styles.categoryCount}>
                                        <Text style={styles.categoryCountText}>{entry.count} 件</Text>
                                    </View>
                                </View>
                            );
                        }
                        return <ItemCard item={entry.item} />;
                    }}
                    refreshControl={
                        <RefreshControl
                            refreshing={refreshing}
                            onRefresh={onRefresh}
                            tintColor={colors.textMuted}
                            colors={[colors.accent]}
                        />
                    }
                    ListEmptyComponent={
                        <Text style={styles.empty}>
                            {scene === '全部' ? '暂无物品' : `${scene}中暂无物品`}
                        </Text>
                    }
                    contentContainerStyle={{ paddingBottom: 160 }}
                />
                {loading && (
                    <ActivityIndicator size="large" color={colors.accent} style={styles.loaderOverlay} />
                )}
            </View>
        );
    }

    // ── Expiring mode ──
    const expiringItems = sceneItems
        .filter((item) => item.status === 'expiring soon' || item.status === 'expired')
        .sort((a, b) => {
            // Expired first
            if (a.status === 'expired' && b.status !== 'expired') return -1;
            if (a.status !== 'expired' && b.status === 'expired') return 1;
            // Then by expiration date
            return a.current_expiration_date.localeCompare(b.current_expiration_date);
        });

    const expiredCount = expiringItems.filter((i) => i.status === 'expired').length;
    const expiringSoonCount = expiringItems.filter((i) => i.status === 'expiring soon').length;

    return (
        <View style={styles.container}>
            <FlatList
                ListHeaderComponent={
                    <View style={styles.headerSection}>
                        <View style={styles.summaryRow}>
                            <View style={styles.summaryPill}>
                                <View style={[styles.summaryDot, { backgroundColor: statusColors.expired }]} />
                                <Text style={styles.summaryText}>已过期 {expiredCount}</Text>
                            </View>
                            <View style={styles.summaryPill}>
                                <View style={[styles.summaryDot, { backgroundColor: statusColors.expiringSoon }]} />
                                <Text style={styles.summaryText}>即将过期 {expiringSoonCount}</Text>
                            </View>
                        </View>
                    </View>
                }
                data={expiringItems}
                keyExtractor={(item) => String(item.id)}
                renderItem={({ item }) => <ItemCard item={item} />}
                refreshControl={
                    <RefreshControl
                        refreshing={refreshing}
                        onRefresh={onRefresh}
                        tintColor={colors.textMuted}
                        colors={[colors.accent]}
                    />
                }
                ListEmptyComponent={
                    <Text style={styles.empty}>
                        太棒了！没有即将过期或已过期的物品 🎉
                    </Text>
                }
                contentContainerStyle={{ paddingBottom: 160 }}
            />
            {loading && (
                <ActivityIndicator size="large" color={colors.accent} style={styles.loaderOverlay} />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.bg },
    loaderOverlay: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        justifyContent: 'center',
        backgroundColor: 'rgba(253,241,240,0.6)',
    },
    headerSection: {
        paddingHorizontal: spacing.xl,
        paddingTop: spacing.xl,
        paddingBottom: spacing.md,
    },
    headerDesc: {
        fontSize: 14,
        color: colors.textMuted,
        lineHeight: 20,
        marginBottom: spacing.md,
    },
    // Categories mode
    categoryHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.xl,
        paddingTop: spacing.lg,
        paddingBottom: spacing.sm,
        gap: spacing.sm,
    },
    categoryBadge: {
        width: 32,
        height: 32,
        borderRadius: 16,
        justifyContent: 'center',
        alignItems: 'center',
    },
    categoryTitle: {
        fontSize: 16,
        fontWeight: '700',
        color: colors.textPrimary,
        flex: 1,
    },
    categoryCount: {
        backgroundColor: colors.accentBg,
        paddingHorizontal: spacing.sm + 2,
        paddingVertical: spacing.xs,
        borderRadius: radius.full,
    },
    categoryCountText: {
        fontSize: 12,
        fontWeight: '600',
        color: colors.accent,
    },
    // Expiring mode
    summaryRow: {
        flexDirection: 'row',
        gap: spacing.md,
    },
    summaryPill: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.chipBg,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        borderRadius: radius.full,
        gap: 6,
        shadowColor: colors.shadowInset,
        shadowOffset: { width: -1, height: -1 },
        shadowOpacity: 0.3,
        shadowRadius: 2,
        elevation: 1,
    },
    summaryDot: {
        width: 10,
        height: 10,
        borderRadius: 5,
    },
    summaryText: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.textSecondary,
    },
    // Item card (reused from ItemListScreen)
    itemCard: {
        marginHorizontal: spacing.xl,
        marginBottom: spacing.md,
        paddingVertical: spacing.xxl,
        paddingHorizontal: spacing.xl,
    },
    itemRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    itemIconCircle: {
        width: 52,
        height: 52,
        borderRadius: 26,
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: spacing.lg,
    },
    itemInfo: { flex: 1, marginRight: spacing.sm },
    itemName: { fontSize: 15, fontWeight: '600', color: colors.textPrimary, marginBottom: 2 },
    itemDesc: { fontSize: 12, color: colors.textMuted },
    itemStatus: { alignItems: 'flex-end' },
    itemQty: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, marginBottom: 2 },
    statusRow: { flexDirection: 'row', alignItems: 'center' },
    statusDot: {
        width: 10,
        height: 10,
        borderRadius: 5,
        marginRight: 6,
    },
    statusText: { fontSize: 11, color: colors.textMuted, fontWeight: '500' },
    empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center', marginTop: 40, paddingHorizontal: spacing.xl },
});
