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

export default function RemindersScreen({ navigation }: Props) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchItems = useCallback(async () => {
    try {
      const res = await api.get('/items/reminders');
      setItems(res.data);
    } catch {
      Alert.alert('Error', 'Failed to load reminders');
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

  const renderItem = ({ item }: { item: Item }) => {
    const isExpired = item.status === 'expired';
    return (
      <TouchableOpacity
        style={[styles.item, isExpired ? styles.itemExpired : styles.itemWarning]}
        onPress={() => navigation.navigate('ItemDetail', { id: item.id })}
      >
        <View style={styles.itemHeader}>
          <Text style={styles.itemName}>{item.name}</Text>
          <Text
            style={[
              styles.statusBadge,
              { backgroundColor: isExpired ? '#fef2f2' : '#fffbeb' },
              { color: isExpired ? '#ef4444' : '#f59e0b' },
            ]}
          >
            {item.status}
          </Text>
        </View>
        <Text style={styles.itemDetail}>
          Expires: {item.current_expiration_date}
        </Text>
        <Text style={styles.itemDetail}>
          {item.location} · {item.quantity_value} {item.quantity_unit}
        </Text>
      </TouchableOpacity>
    );
  };

  if (loading) {
    return (
      <ActivityIndicator size="large" color="#8b5cf6" style={styles.loader} />
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderItem}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>✅</Text>
            <Text style={styles.emptyTitle}>All Clear!</Text>
            <Text style={styles.emptySubtitle}>
              No items expiring soon or expired.
            </Text>
          </View>
        }
        contentContainerStyle={
          items.length === 0 ? styles.emptyFull : undefined
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  loader: { flex: 1, justifyContent: 'center' },
  item: {
    marginHorizontal: 12,
    marginTop: 10,
    padding: 14,
    borderRadius: 10,
    borderLeftWidth: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  itemWarning: {
    backgroundColor: '#fffbeb',
    borderLeftColor: '#f59e0b',
  },
  itemExpired: {
    backgroundColor: '#fef2f2',
    borderLeftColor: '#ef4444',
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: 'bold', color: '#111827', flex: 1 },
  statusBadge: {
    fontSize: 12,
    fontWeight: 'bold',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    overflow: 'hidden',
  },
  itemDetail: { fontSize: 13, color: '#6b7280', marginTop: 4 },
  emptyContainer: { alignItems: 'center', paddingTop: 60 },
  emptyFull: { flex: 1, justifyContent: 'center' },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { fontSize: 20, fontWeight: 'bold', color: '#111827' },
  emptySubtitle: { fontSize: 14, color: '#6b7280', marginTop: 4 },
});
