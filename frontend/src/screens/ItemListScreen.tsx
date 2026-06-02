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
import { neoRaised, neoChip, colors, spacing, radius } from '../theme';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const STATUS_COLORS: Record<string, string> = {
  active: '#2ecc71',
  'expiring soon': '#f39c12',
  expired: '#e74c3c',
  consumed: '#95a5a6',
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

  const getStatusStyle = (status: string) => ({
    color: STATUS_COLORS[status] || '#95a5a6',
    fontWeight: 'bold' as const,
    fontSize: 12,
  });

  const formatQuantity = (item: Item) =>
    `${item.quantity_value} ${item.quantity_unit}`;

  const renderItem = ({ item }: { item: Item }) => (
    <TouchableOpacity
      style={styles.item}
      onPress={() => navigation.navigate('ItemDetail', { id: item.id })}
    >
      <View style={styles.itemHeader}>
        <Text style={styles.itemName}>{item.name}</Text>
        <View style={styles.statusBadge}>
          <Text style={getStatusStyle(item.status)}>
            {item.status === 'active' ? '有效' : item.status === 'expiring soon' ? '即将过期' : item.status === 'expired' ? '已过期' : item.status === 'consumed' ? '已消耗' : item.status}
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
            style={[styles.filterChip, filter === f.value && styles.filterChipActive]}
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
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
          ListEmptyComponent={
            <Text style={styles.empty}>暂无物品</Text>
          }
          contentContainerStyle={items.length === 0 ? styles.emptyContainer : { paddingBottom: 80 }}
        />
      )}

      <TouchableOpacity
        style={styles.fab}
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
    padding: spacing.sm,
    gap: spacing.sm - 2,
    backgroundColor: colors.bg,
  },
  filterChip: {
    ...neoChip(false),
  },
  filterChipActive: {
    ...neoChip(true),
  },
  filterChipText: {
    fontSize: 13,
    color: colors.textSecondary,
  },
  filterChipTextActive: {
    color: colors.white,
    fontWeight: 'bold',
  },
  item: {
    ...neoRaised,
    marginHorizontal: spacing.lg - 4,
    marginTop: spacing.md - 2,
    padding: spacing.lg - 2,
  },
  statusBadge: {
    backgroundColor: colors.white,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.5)',
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: 'bold', color: colors.textPrimary, flex: 1 },
  itemSubtitle: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.xs + 1 },
  itemDetails: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.sm - 2,
  },
  itemDetail: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.xs - 1 },
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
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: colors.shadowDark2,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.5,
    shadowRadius: 10,
    elevation: 8,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  fabText: { fontSize: 28, color: colors.white, lineHeight: 30 },
});
