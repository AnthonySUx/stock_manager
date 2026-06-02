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

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  'expiring soon': '#f59e0b',
  expired: '#ef4444',
  consumed: '#6b7280',
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
    color: STATUS_COLORS[status] || '#6b7280',
    fontWeight: 'bold' as const,
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
        <Text style={getStatusStyle(item.status)}>{item.status === 'active' ? '有效' : item.status === 'expiring soon' ? '即将过期' : item.status === 'expired' ? '已过期' : item.status === 'consumed' ? '已消耗' : item.status}</Text>
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
            style={[
              styles.filterChip,
              filter === f.value && styles.filterChipActive,
            ]}
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
        <ActivityIndicator size="large" color="#8b5cf6" style={styles.loader} />
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
          contentContainerStyle={items.length === 0 ? styles.emptyContainer : undefined}
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
  container: { flex: 1, backgroundColor: '#f8fafc' },
  loader: { flex: 1, justifyContent: 'center' },
  filterRow: {
    flexDirection: 'row',
    padding: 8,
    gap: 6,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f3f4f6',
  },
  filterChipActive: {
    backgroundColor: '#8b5cf6',
  },
  filterChipText: {
    fontSize: 13,
    color: '#374151',
  },
  filterChipTextActive: {
    color: '#fff',
    fontWeight: 'bold',
  },
  item: {
    backgroundColor: '#fff',
    marginHorizontal: 12,
    marginTop: 10,
    padding: 14,
    borderRadius: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: 'bold', color: '#111827', flex: 1 },
  itemSubtitle: { fontSize: 13, color: '#6b7280', marginTop: 2 },
  itemDetails: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 6,
  },
  itemDetail: { fontSize: 13, color: '#4b5563', marginTop: 2 },
  empty: { fontSize: 16, color: '#9ca3af', textAlign: 'center' },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#8b5cf6',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#8b5cf6',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  fabText: { fontSize: 28, color: '#fff', lineHeight: 30 },
});
