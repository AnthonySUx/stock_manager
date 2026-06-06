import React, { useCallback, useState, useEffect, useRef, useMemo } from 'react';
import {
    Animated,
    Dimensions,
    PanResponder,
    ActivityIndicator,
    Alert,
    FlatList,
    RefreshControl,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
    Pressable,
    Keyboard,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRoute } from '@react-navigation/native';

import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import type { Item } from '../types';
import { colors, spacing, radius, status } from '../theme';
import { NeuOut, NeuIn, PressableScale, NeuIconBtn } from '../components/NeoComponents';
import { Ionicons } from '@expo/vector-icons';

type Props = {
    navigation: NativeStackNavigationProp<any>;
};

const STATUS_COLORS: Record<string, string> = {
    active: status.active,
    'expiring soon': status.expiringSoon,
    expired: status.expired,
    consumed: colors.textMuted,
};

const STATUS_LABELS: Record<string, string> = {
    active: '正常',
    'expiring soon': '即将过期',
    expired: '已过期',
    consumed: '已消耗',
};

const STATUS_PRIORITY: Record<string, number> = {
    expired: 0,
    'expiring soon': 1,
    active: 2,
    consumed: 3,
};

export default function ItemListScreen({ navigation }: Props) {
    const [allItems, setAllItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [filter, setFilter] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const searchInputRef = useRef<TextInput>(null);
    const route = useRoute<any>();
    const [scene, setScene] = useState<string>('全部');

    // Removed: scene is now updated via onSelectScene callback, no need for route.params sync
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

    const formatQuantity = (item: Item) =>
        `${item.quantity_value} ${item.quantity_unit}`;

    // Compute stats
    const sceneItems = scene === '全部'
        ? allItems
        : allItems.filter((item) => item.location === scene);
    const expiringSoonCount = sceneItems.filter(
        (item) => item.status === 'expiring soon'
    ).length;
    const expiredCount = sceneItems.filter(
        (item) => item.status === 'expired'
    ).length;

    // Search + filter
    const filteredItems = (scene === '全部'
        ? allItems
        : allItems.filter((item) => item.location === scene)
    ).filter((item) => (filter ? item.status === filter : true))
        .filter((item) => {
            if (!searchQuery.trim()) return true;
            const q = searchQuery.toLowerCase();
            return (
                item.name.toLowerCase().includes(q) ||
                (item.category || '').toLowerCase().includes(q) ||
                (item.location || '').toLowerCase().includes(q) ||
                (item.owner || '').toLowerCase().includes(q)
            );
        });
    const sortedItems = [...filteredItems].sort((a, b) => {
        const pa = STATUS_PRIORITY[a.status] ?? 4;
        const pb = STATUS_PRIORITY[b.status] ?? 4;
        return pa - pb;
    });

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

    const getStatusMeta = (item: Item): { label: string; color: string; text: string } => {
        if (item.status === 'expired') return { label: '已过期', color: status.expired, text: '已过期' };
        if (item.status === 'expiring soon') return { label: '即将过期', color: status.expiringSoon, text: '即将过期' };
        if (item.status === 'consumed') return { label: '已消耗', color: colors.textMuted, text: '已消耗' };
        return { label: '有效', color: status.active, text: '充足' };
    };

    const renderItem = ({ item }: { item: Item }) => {
        const meta = getStatusMeta(item);
        const iconName = getItemIcon(item);
        return (
            <PressableScale
                onPress={() => navigation.navigate('ItemDetail', { id: item.id })}
                scaleIn={0.97}
            >
                <NeuOut borderRadius={36} depth="sm" style={styles.itemCard}>
                    <View style={styles.itemRow}>
                        {/* Left: inset icon circle */}
                        <NeuIn borderRadius={50} depth="sm" style={styles.itemIconCircle}>
                            <Ionicons name={iconName} size={22} color={colors.accent} />
                        </NeuIn>

                        {/* Center: item info */}
                        <View style={styles.itemInfo}>
                            <Text style={styles.itemName} numberOfLines={1}>{item.name}</Text>
                            <Text style={styles.itemDesc} numberOfLines={1}>
                                {item.location} · {item.category || '未分类'}
                            </Text>
                        </View>

                        {/* Right: quantity + status */}
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

    const FILTERS: { label: string; value: string | null }[] = [
        { label: '全部', value: null },
        { label: '正常', value: 'active' },
        { label: '即将过期', value: 'expiring soon' },
        { label: '已过期', value: 'expired' },
    ];

    const insets = useSafeAreaInsets();


    // === Draggable FAB — Magnetic Snap-to-Edge ===
    const fabSize = 62;
    const fabPadding = spacing.xl;
    const bottomReserve = 122;
    const headerReserve = 80;

    const insetsRef = useRef(insets);
    insetsRef.current = insets;

    const getDefaultX = () => Dimensions.get('window').width - fabPadding - fabSize;
    const getDefaultY = () => Dimensions.get('window').height - bottomReserve - fabSize;

    // Animated values for rendering
    const posX = useRef(new Animated.Value(getDefaultX())).current;
    const posY = useRef(new Animated.Value(getDefaultY())).current;

    const isDragging = useRef(false);
    const dragStartX = useRef(0);
    const dragStartY = useRef(0);

    const getBounds = useCallback(() => {
        const { width: winW, height: winH } = Dimensions.get('window');
        const { top, bottom } = insetsRef.current;
        return {
            minX: fabPadding,
            maxX: winW - fabPadding - fabSize,
            minY: top + headerReserve,
            maxY: winH - bottom - bottomReserve - fabSize,
        };
    }, []);

    const clampPoint = useCallback((x: number, y: number) => {
        const b = getBounds();
        return {
            x: Math.min(Math.max(x, b.minX), b.maxX),
            y: Math.min(Math.max(y, b.minY), b.maxY),
        };
    }, []);

    const panResponder = useRef(PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 3 || Math.abs(g.dy) > 3,
        onPanResponderGrant: () => {
            isDragging.current = false;
            // Cancel any ongoing snap animation and capture current position
            posX.stopAnimation((v) => { dragStartX.current = v; });
            posY.stopAnimation((v) => { dragStartY.current = v; });
        },
        onPanResponderMove: (_, gesture) => {
            if (Math.abs(gesture.dx) > 5 || Math.abs(gesture.dy) > 5) {
                isDragging.current = true;
            }
            // Use grant-time position + cumulative gesture delta (NOT _value + dx)
            const clamped = clampPoint(dragStartX.current + gesture.dx, dragStartY.current + gesture.dy);
            posX.setValue(clamped.x);
            posY.setValue(clamped.y);
        },
        onPanResponderRelease: (_, gesture) => {
            if (!isDragging.current) {
                // Tap — navigate
                navigation.navigate('AddItem');
                return;
            }
            const releaseX = dragStartX.current + gesture.dx;
            const releaseY = dragStartY.current + gesture.dy;

            // Clamp current visual position to bounds
            const rx = clampPoint(releaseX, releaseY).x;
            const ry = clampPoint(releaseX, releaseY).y;

            // Calculate inertia direction & distance from velocity (or displacement)
            const speed = Math.sqrt(gesture.vx * gesture.vx + gesture.vy * gesture.vy);
            const dist = Math.sqrt(gesture.dx * gesture.dx + gesture.dy * gesture.dy);

            let dirX: number, dirY: number;
            let inertiaDist: number;

            if (speed > 0.1) {
                inertiaDist = Math.min(speed * 100, 160);
                dirX = gesture.vx / speed;
                dirY = gesture.vy / speed;
            } else if (dist > 10) {
                inertiaDist = Math.min(dist * 0.5, 100);
                dirX = gesture.dx / dist;
                dirY = gesture.dy / dist;
            } else {
                dirX = 0;
                dirY = 0;
                inertiaDist = 0;
            }

            let targetX: number;
            let targetY: number;
            const b = getBounds();

            if (dirX === 0 && dirY === 0) {
                // No direction — snap to nearest edge
                const dL = rx - b.minX;
                const dR = b.maxX - rx;
                const dT = ry - b.minY;
                const dB = b.maxY - ry;
                const minD = Math.min(dL, dR, dT, dB);
                if (minD === dL) { targetX = b.minX; targetY = ry; }
                else if (minD === dR) { targetX = b.maxX; targetY = ry; }
                else if (minD === dT) { targetX = rx; targetY = b.minY; }
                else { targetX = rx; targetY = b.maxY; }
            } else {
                // Project endpoint along direction
                const px = rx + dirX * inertiaDist;
                const py = ry + dirY * inertiaDist;

                // Raycast: find first boundary intersection along direction
                let bestT = Infinity;
                let hitX = px;
                let hitY = py;

                // Left edge
                if (dirX < 0) {
                    const t = (b.minX - rx) / dirX;
                    const y = ry + t * dirY;
                    const d = Math.sqrt((b.minX - rx) ** 2 + (y - ry) ** 2);
                    if (t > 0 && d <= inertiaDist && y >= b.minY && y <= b.maxY && t < bestT) {
                        bestT = t; hitX = b.minX; hitY = y;
                    }
                }
                // Right edge
                if (dirX > 0) {
                    const t = (b.maxX - rx) / dirX;
                    const y = ry + t * dirY;
                    const d = Math.sqrt((b.maxX - rx) ** 2 + (y - ry) ** 2);
                    if (t > 0 && d <= inertiaDist && y >= b.minY && y <= b.maxY && t < bestT) {
                        bestT = t; hitX = b.maxX; hitY = y;
                    }
                }
                // Top edge
                if (dirY < 0) {
                    const t = (b.minY - ry) / dirY;
                    const x = rx + t * dirX;
                    const d = Math.sqrt((x - rx) ** 2 + (b.minY - ry) ** 2);
                    if (t > 0 && d <= inertiaDist && x >= b.minX && x <= b.maxX && t < bestT) {
                        bestT = t; hitX = x; hitY = b.minY;
                    }
                }
                // Bottom edge
                if (dirY > 0) {
                    const t = (b.maxY - ry) / dirY;
                    const x = rx + t * dirX;
                    const d = Math.sqrt((x - rx) ** 2 + (b.maxY - ry) ** 2);
                    if (t > 0 && d <= inertiaDist && x >= b.minX && x <= b.maxX && t < bestT) {
                        bestT = t; hitX = x; hitY = b.maxY;
                    }
                }

                // If ray hit a boundary, use intersection; otherwise use projected point clamped
                if (bestT < Infinity) {
                    targetX = hitX;
                    targetY = hitY;
                } else {
                    targetX = Math.min(Math.max(px, b.minX), b.maxX);
                    targetY = Math.min(Math.max(py, b.minY), b.maxY);
                }
            }

            // Smooth XY animation along the glide path
            Animated.parallel([
                Animated.timing(posX, {
                    toValue: targetX,
                    duration: 200,
                    useNativeDriver: false,
                }),
                Animated.timing(posY, {
                    toValue: targetY,
                    duration: 200,
                    useNativeDriver: false,
                }),
            ]).start();
        },
    })).current;

    return (
        <View style={styles.container}>
            {/* Header */}
            <View style={[styles.headerArea, { paddingTop: insets.top + spacing.sm }]}>
                <View style={styles.headerTopRow}>
                    <PressableScale
                        onPress={() => navigation.navigate('SceneSelect', { currentScene: scene, onSelectScene: (s: string) => setScene(s) })}
                        scaleIn={0.95}
                    >
                        <View style={styles.sceneBtn}>
                            <Ionicons name="location-outline" size={14} color={colors.accent} />
                            <Text style={styles.sceneBtnText}>{scene === '全部' ? '全部场景' : scene}</Text>
                            <Ionicons name="chevron-down" size={12} color={colors.textMuted} />
                        </View>
                    </PressableScale>
                    <PressableScale
                        onPress={() => navigation.navigate('RestockList')}
                        scaleIn={0.92}
                    >
                        <NeuIconBtn size={52} backgroundColor={colors.accentBg}>
                            <Ionicons name="list-outline" size={27} color={colors.accent} />
                        </NeuIconBtn>
                    </PressableScale>
                </View>
                <Text style={styles.screenTitle}>库存管理</Text>
            </View>

            {loading ? (
                <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
            ) : (
                <FlatList
                    ListHeaderComponent={
                        <View>
                            {/* Search bar — NeuIn as absolute background for shadows, content layer on top for reliable input */}
                            <View style={[styles.searchBar, styles.searchBarLayer]}>
                                {/* Background decoration: Neumorphic inset shadow via Skia — no children, pure visual */}
                                <NeuIn borderRadius={27} depth="md" style={StyleSheet.absoluteFill} />
                                {/* Content layer: icon + TextInput — fully interactive, no Skia interference */}
                                <View style={styles.searchRow}>
                                    <Ionicons name="search" size={18} color={colors.textMuted} style={styles.searchIcon} />
                                    <TextInput
                                        ref={searchInputRef}
                                        style={styles.searchInput}
                                        value={searchQuery}
                                        onChangeText={setSearchQuery}
                                        placeholder="搜索库存物品或分类..."
                                        placeholderTextColor={colors.textMuted}
                                        returnKeyType="search"
                                        onSubmitEditing={() => Keyboard.dismiss()}
                                    />
                                </View>
                            </View>

                            {/* Dashboard cards */}
                            <View style={styles.dashboardGrid}>
                                <PressableScale
                                    onPress={() => navigation.navigate('InventorySummary', {
                                        mode: 'categories',
                                        title: '总类目',
                                        scene,
                                    })}
                                    scaleIn={0.95}
                                    style={{ flex: 1 }}
                                >
                                    <NeuOut borderRadius={36} depth="sm" style={styles.statCard}>
                                        <Text style={styles.statNumber}>{sceneItems.length}</Text>
                                        <Text style={styles.statLabel}>总类目</Text>
                                    </NeuOut>
                                </PressableScale>
                                <PressableScale
                                    onPress={() => navigation.navigate('InventorySummary', {
                                        mode: 'expiring',
                                        title: '即将过期',
                                        scene,
                                    })}
                                    scaleIn={0.95}
                                    style={{ flex: 1 }}
                                >
                                    <NeuOut borderRadius={36} depth="sm" style={styles.statCard}>
                                        <Text style={[styles.statNumber, { color: colors.warning }]}>
                                            {expiringSoonCount + expiredCount}
                                        </Text>
                                        <Text style={styles.statLabel}>即将过期</Text>
                                    </NeuOut>
                                </PressableScale>
                            </View>

                            {/* Section title */}
                            <Text style={styles.sectionTitle}>我的库存</Text>

                            {/* Filter chips */}
                            <View style={styles.filterRow}>
                                {FILTERS.map((f) => {
                                    const isActive = filter === f.value;
                                    return (
                                        <TouchableOpacity
                                            key={f.label}
                                            activeOpacity={0.7}
                                            onPress={() => setFilter(f.value)}
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
                        </View>
                    }
                    data={sortedItems}
                    keyExtractor={(item) => String(item.id)}
                    renderItem={renderItem}
                    refreshControl={
                        < RefreshControl
                            refreshing={refreshing}
                            onRefresh={onRefresh}
                            tintColor={colors.textMuted}
                            colors={[colors.accent]}
                        />
                    }
                    ListEmptyComponent={
                        < Text style={styles.empty} >
                            {searchQuery ? '未找到匹配的物品' : scene === '全部' ? '暂无物品' : `${scene}中暂无物品`}
                        </Text >
                    }
                    contentContainerStyle={{ paddingBottom: 160 }}
                />
            )}

            {/* FAB - Draggable Magnetic Snap */}
            <Animated.View
                style={[
                    styles.fab,
                    { left: posX, top: posY },
                ]}
                {...panResponder.panHandlers}
            >
                <Ionicons name="add" size={30} color="#ffffff" />
            </Animated.View>
        </View >
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
    headerRightBtn: {
        width: 52,
        height: 52,
        borderRadius: 26,
        backgroundColor: colors.accentBg,
        justifyContent: 'center',
        alignItems: 'center',
    },
    sceneBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        alignSelf: 'flex-start',
        backgroundColor: colors.bg,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.sm + 2,
        borderRadius: radius.full,
        gap: 6,
        shadowColor: colors.shadowDark,
        shadowOffset: { width: 3, height: 3 },
        shadowOpacity: 0.35,
        shadowRadius: 8,
        elevation: 4,
        borderTopWidth: 0.5,
        borderLeftWidth: 0.5,
        borderRightWidth: 0,
        borderBottomWidth: 0,
        borderColor: 'rgba(255,255,255,0.50)',
    },
    sceneBtnText: {
        fontSize: 13,
        fontWeight: '500',
        color: colors.textSecondary,
    },
    // Search bar - capsule
    searchBar: {
        marginHorizontal: spacing.xl,
        marginTop: spacing.md,
        marginBottom: spacing.xl,
        height: 54,
        justifyContent: 'center',
    },
    // Container that positions the NeuIn background layer
    searchBarLayer: {
        position: 'relative',
    },
    searchRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.xl,
        flex: 1,
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
    // Dashboard
    dashboardGrid: {
        flexDirection: 'row',
        paddingHorizontal: spacing.xl,
        gap: spacing.lg,
        marginBottom: spacing.xxl,
    },
    statCard: {
        flex: 1,
        paddingVertical: 24,
        paddingHorizontal: 20,
        alignItems: 'center',
    },
    statNumber: {
        fontSize: 34,
        fontWeight: '700',
        color: colors.accent,
        marginBottom: 4,
    },
    statLabel: {
        fontSize: 13,
        color: colors.textMuted,
        fontWeight: '600',
    },
    // Section title
    sectionTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: colors.textPrimary,
        marginHorizontal: spacing.xl,
        marginBottom: spacing.md,
    },
    // Filter row
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
    filterChipActive: {
        paddingHorizontal: 14,
        paddingVertical: 6,
    },
    filterChipTextActive: { fontSize: 13, color: colors.accent, fontWeight: '600' },
    // Item card
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
    empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center', marginTop: 40 },
    // FAB
    fab: {
        position: 'absolute',
        width: 62,
        height: 62,
        borderRadius: 31,
        backgroundColor: colors.accent,
        justifyContent: 'center' as const,
        alignItems: 'center' as const,
        borderWidth: 0,
        // Glow shadow
        shadowColor: 'rgba(255, 107, 87, 0.4)',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.6,
        shadowRadius: 12,
        elevation: 8,
        zIndex: 999,
    },
});
