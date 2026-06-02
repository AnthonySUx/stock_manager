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
import type { RestockItem } from '../types';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export default function RestockListScreen({ navigation }: Props) {
  const [items, setItems] = useState<RestockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<string | null>('pending');

  const fetchItems = useCallback(async (status?: string | null) => {
    try {
      const params = status ? { status } : {};
      const res = await api.get('/restock', { params });
      setItems(res.data);
    } catch {
      Alert.alert('Error', 'Failed to load restock items');
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

  const formatQuantity = (item: RestockItem) => {
    if (item.quantity_value == null) return '-';
    return `${item.quantity_value} ${item.quantity_unit || ''}`.trim();
  };

  const handleDone = async (item: RestockItem) => {
    navigation.navigate('DoneRestock', { id: item.id, item });
  };

  const handleDelete = (item: RestockItem) => {
    Alert.alert('Delete', `Delete "${item.name}" from restock list?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await api.delete(`/restock/${item.id}`);
            fetchItems(filter);
          } catch {
            Alert.alert('Error', 'Failed to delete');
          }
        },
      },
    ]);
  };

  const renderItem = ({ item }: { item: RestockItem }) => (
    <View style={styles.item}>
      <View style={styles.itemHeader}>
        <Text style={styles.itemName}>{item.name}</Text>
        <Text
          style={[
            styles.itemStatus,
            { color: item.status === 'pending' ? '#f59e0b' : '#22c55e' },
          ]}
        >
          {item.status}
        </Text>
      </View>
      {item.category && (
        <Text style={styles.itemDetail}>{item.category}</Text>
      )}
      <Text style={styles.itemDetail}>Qty: {formatQuantity(item)}</Text>
      {item.status === 'pending' && (
        <View style={styles.itemActions}>
          <TouchableOpacity
            style={styles.doneBtn}
            onPress={() => handleDone(item)}
          >
            <Text style={styles.doneBtnText}>✅ Done</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.deleteSmallBtn}
            onPress={() => handleDelete(item)}
          >
            <Text style={styles.deleteSmallBtnText}>🗑️</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.filterRow}>
        {[
          { label: 'Pending', value: 'pending' },
          { label: 'Done', value: 'done' },
          { label: 'All', value: null },
        ].map((f) => (
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
            <Text style={styles.empty}>No restock items</Text>
          }
          contentContainerStyle={
            items.length === 0 ? styles.emptyContainer : undefined
          }
        />
      )}

      <TouchableOpacity
        style={styles.fab}
        onPress={() => navigation.navigate('AddRestock')}
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
  filterChipActive: { backgroundColor: '#8b5cf6' },
  filterChipText: { fontSize: 13, color: '#374151' },
  filterChipTextActive: { color: '#fff', fontWeight: 'bold' },
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
  itemStatus: { fontSize: 13, fontWeight: 'bold' },
  itemDetail: { fontSize: 13, color: '#6b7280', marginTop: 3 },
  itemActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    marginTop: 8,
    gap: 8,
  },
  doneBtn: {
    backgroundColor: '#22c55e',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  doneBtnText: { color: '#fff', fontWeight: 'bold', fontSize: 14 },
  deleteSmallBtn: {
    padding: 8,
  },
  deleteSmallBtnText: { fontSize: 18 },
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
