import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import type { Item } from '../types';
import { neoCard, neoFilterChip, neoBadge, colors, spacing, radius, shadowXl } from '../theme';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const STATUS_COLORS: Record<string, string> = {
  active: '#10b981',
  'expiring soon': '#f59e0b',
  expired: '#ef4444',
  consumed: '#94a3b8',
};

const STATUS_BG: Record<string, string> = {
  active: '#d1fae5',
  'expiring soon': '#fef3c7',
  expired: '#fde8e8',
  consumed: '#f1f5f9',
};

const STATUS_LABELS: Record<string, string> = {
  active: '有效',
  'expiring soon': '即将过期',
  expired: '已过期',
  consumed: '已消耗',
};

export default function ItemListScreen({ navigation }: Props) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);

  const fetchItems = useCallback(async (status?: string | null) => {
    try {
      const params = status ? { status } : {};
      const res = await api.get('/items', { params });
      setItems(res.data);
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
      fetchItems(filter);
    }, [filter, fetchItems])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchItems(filter);
  };

  const formatQuantity = (item: Item) =>
    `${item.quantity_value} ${item.quantity_unit}`;

  const renderItem = ({ item }: { item: Item }) => (
    <TouchableOpacity
      style={styles.item}
      activeOpacity={0.85}
      onPress={() => navigation.navigate('ItemDetail', { id: item.id })}
    >
      <View style={styles.itemHeader}>
        <Text style={styles.itemName} numberOfLines={1}>{item.name}</Text>
        <View style={[styles.statusBadge, { backgroundColor: STATUS_BG[item.status] || '#f1f5f9' }]}>
          <Text style={[styles.statusText, { color: STATUS_COLORS[item.status] || '#94a3b8' }]}>
            {STATUS_LABELS[item.status] || item.status}
          </Text>
        </View>
      </View>
      <Text style={styles.itemSubtitle}>
        {item.category} · {item.owner}
      </Text>
      <View style={styles.itemDetails}>
        <Text style={styles.itemDetail}>
          数量: {formatQuantity(item)}
        </Text>
        <Text style={styles.itemDetail}>📍 {item.location}</Text>
      </View>
      <Text style={styles.itemDetail}>
        过期: {item.current_expiration_date}
      </Text>
    </TouchableOpacity>
  );

  const FILTERS: { label: string; value: string | null }[] = [
    { label: '全部', value: null },
    { label: '有效', value: 'active' },
    { label: '即将过期', value: 'expiring soon' },
    { label: '已过期', value: 'expired' },
  ];

  return (
    <View style={styles.container}>
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

      {loading ? (
        <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
      ) : (
        <FlatList
          data={items}
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
            <Text style={styles.empty}>暂无物品</Text>
          }
          contentContainerStyle={items.length === 0 ? styles.emptyContainer : { paddingBottom: 80 }}
        />
      )}

      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('AddItem')}
      >
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.md,
    gap: spacing.sm - 2,
    backgroundColor: colors.bg,
  },
  filterChipText: {
    fontSize: 13,
    color: colors.textSecondary,
  },
  filterChipTextActive: {
    color: colors.white,
    fontWeight: '600',
  },
  item: {
    ...neoCard,
    marginHorizontal: spacing.lg - 2,
    marginTop: spacing.md,
    padding: spacing.lg,
  },
  statusBadge: {
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    marginLeft: spacing.sm,
  },
  statusText: { fontSize: 12, fontWeight: '700' },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, flex: 1 },
  itemSubtitle: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.xs + 1 },
  itemDetails: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
  },
  itemDetail: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.xs },
  empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center' },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  fab: {
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
});
