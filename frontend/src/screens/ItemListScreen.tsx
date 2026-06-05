import React, { useCallback, useState, useEffect } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  Keyboard,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRoute } from '@react-navigation/native';

import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import type { Item } from '../types';
import { neoCard, neoFilterChip, neoBadge, neoInput, neuOut, neuIn, colors, spacing, radius, shadowXl } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const STATUS_COLORS: Record<string, string> = {
  active: '#2ED573',
  'expiring soon': '#FFA502',
  expired: '#FF4757',
  consumed: '#94a3b8',
};

const STATUS_LABELS: Record<string, string> = {
  active: '有效',
  'expiring soon': '即将过期',
  expired: '已过期',
  consumed: '已消耗',
};

export default function ItemListScreen({ navigation }: Props) {
  const [allItems, setAllItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const route = useRoute<any>();
  const [scene, setScene] = useState<string>('全部');

  useEffect(() => {
    const newScene = route.params?.selectedScene;
    if (newScene && newScene !== scene) {
      setScene(newScene);
    }
  }, [route.params?.selectedScene, scene]);

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

  const getStatusMeta = (item: Item): { label: string; dotColor: string; text: string } => {
    if (item.status === 'expired') return { label: '已过期', dotColor: '#FF4757', text: '已过期' };
    if (item.status === 'expiring soon') return { label: '即将过期', dotColor: '#FFA502', text: '即将过期' };
    if (item.status === 'consumed') return { label: '已消耗', dotColor: '#94a3b8', text: '已消耗' };
    return { label: '正常', dotColor: '#2ED573', text: '保质期充足' };
  };

  const renderItem = ({ item }: { item: Item }) => {
    const meta = getStatusMeta(item);
    const iconName = getItemIcon(item);
    return (
      <TouchableOpacity
        style={styles.itemCard}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('ItemDetail', { id: item.id })}
      >
        <View style={styles.itemIconCircle}>
          <Ionicons name={iconName} size={20} color={colors.accent} />
        </View>
        <View style={styles.itemInfo}>
          <Text style={styles.itemName} numberOfLines={1}>{item.name}</Text>
          <Text style={styles.itemDesc} numberOfLines={1}>{item.location} · {item.category || '未分类'}</Text>
        </View>
        <View style={styles.itemStatus}>
          <Text style={styles.itemQty}>{formatQuantity(item)}</Text>
          <View style={styles.statusRow}>
            <View style={[styles.statusDot, { backgroundColor: meta.dotColor }]} />
            <Text style={styles.statusText}>{meta.text}</Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  const FILTERS: { label: string; value: string | null }[] = [
    { label: '全部', value: null },
    { label: '正常', value: 'active' },
    { label: '即将过期', value: 'expiring soon' },
    { label: '已过期', value: 'expired' },
  ];

  const insets = useSafeAreaInsets();

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={[styles.headerArea, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.headerTopRow}>
          <TouchableOpacity
            style={styles.sceneBtn}
            activeOpacity={0.75}
            onPress={() => navigation.navigate('SceneSelect', { currentScene: scene })}
          >
            <Text style={styles.sceneBtnText}>{scene === '全部' ? '全部场景' : scene}</Text>
            <Ionicons name="chevron-down" size={14} color={colors.accent} />
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => navigation.navigate('RestockList')}
            style={styles.headerRightBtn}
          >
            <Ionicons name="cart-outline" size={24} color={colors.accent} />
          </TouchableOpacity>
        </View>
        <Text style={styles.screenTitle}>库存管理</Text>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
      ) : (
        <FlatList
          ListHeaderComponent={
            <View>
              {/* Search bar - capsular */}
              <View style={styles.searchBar}>
                <Ionicons name="search" size={16} color={colors.textMuted} style={{ marginRight: 10 }} />
                <TextInput
                  style={styles.searchInput}
                  value={searchQuery}
                  onChangeText={setSearchQuery}
                  placeholder="搜索库存物品或分类..."
                  placeholderTextColor={colors.textMuted}
                  returnKeyType="search"
                  onSubmitEditing={() => Keyboard.dismiss()}
                />
              </View>

              {/* Dashboard */}
              <View style={styles.dashboardGrid}>
                <View style={styles.statCard}>
                  <Text style={styles.statNumber}>{sceneItems.length}</Text>
                  <Text style={styles.statLabel}>总类目</Text>
                </View>
                <View style={styles.statCard}>
                  <Text style={[styles.statNumber, { color: colors.warning }]}>
                    {expiringSoonCount + expiredCount}
                  </Text>
                  <Text style={styles.statLabel}>即将过期</Text>
                </View>
              </View>

              {/* Section title */}
              <Text style={styles.sectionTitle}>我的库存</Text>

              {/* Filter chips */}
              <View style={styles.filterRow}>
                {FILTERS.map((f) => (
                  <TouchableOpacity
                    key={f.label}
                    style={neoFilterChip(filter === f.value)}
                    activeOpacity={0.7}
                    onPress={() => setFilter(f.value)}
                  >
                    <Text
                      style={[
                        styles.filterChipText,
                        filter === f.value && styles.filterChipTextActive,
                      ]}
                    >
                      {f.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          }
          data={filteredItems}
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
          ListEmptyComponent={
            <Text style={styles.empty}>
              {searchQuery ? '未找到匹配的物品' : scene === '全部' ? '暂无物品' : `${scene}中暂无物品`}
            </Text>
          }
          contentContainerStyle={{ paddingBottom: 130 }}
        />
      )}

      {/* FAB */}
      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('AddItem')}
      >
        <Ionicons name="add" size={28} color="#ffffff" />
      </TouchableOpacity>
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
  headerRightBtn: {
    padding: spacing.sm,
  },
  sceneBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: colors.chipBg,
    paddingHorizontal: spacing.md + 2,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.full,
    gap: 4,
    // subtle inset
    shadowColor: colors.shadowInset,
    shadowOffset: { width: -1, height: -1 },
    shadowOpacity: 0.3,
    shadowRadius: 2,
    elevation: 1,
  },
  sceneBtnText: {
    fontSize: 13,
    fontWeight: '500',
    color: colors.textSecondary,
  },
  // Search bar - capsule
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: spacing.xl,
    marginTop: spacing.md,
    marginBottom: spacing.xl,
    paddingHorizontal: spacing.xl,
    height: 50,
    borderRadius: 25,
    backgroundColor: colors.inputBg,
    shadowColor: colors.shadowInset,
    shadowOffset: { width: -2, height: -2 },
    shadowOpacity: 0.5,
    shadowRadius: 3,
    elevation: 1,
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
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    borderRadius: 30,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 5,
  },
  statNumber: {
    fontSize: 32,
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
  filterChipText: { fontSize: 13, color: colors.textSecondary },
  filterChipTextActive: { color: colors.white, fontWeight: '600' },
  // Item card
  itemCard: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: spacing.xl,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.lg,
    borderRadius: 30,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 5, height: 5 },
    shadowOpacity: 0.36,
    shadowRadius: 10,
    elevation: 4,
  },
  itemIconCircle: {
    width: 50,
    height: 50,
    borderRadius: 25,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.lg,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowInset,
    shadowOffset: { width: -2, height: -2 },
    shadowOpacity: 0.5,
    shadowRadius: 3,
    elevation: 1,
  },
  itemInfo: { flex: 1 },
  itemName: { fontSize: 15, fontWeight: '600', color: colors.textPrimary, marginBottom: 2 },
  itemDesc: { fontSize: 12, color: colors.textMuted },
  itemStatus: { alignItems: 'flex-end' },
  itemQty: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, marginBottom: 2 },
  statusRow: { flexDirection: 'row', alignItems: 'center' },
  statusDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    marginRight: 4,
  },
  statusText: { fontSize: 11, color: colors.textMuted },
  empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center', marginTop: 40 },
  // FAB
  fab: {
    position: 'absolute',
    right: spacing.xl,
    bottom: 110,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.accent,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    borderWidth: 0,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.4,
    shadowRadius: 14,
    elevation: 8,
  },
});
