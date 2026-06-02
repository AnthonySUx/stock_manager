import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import type { Item } from '../types';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export default function ItemDetailScreen({ navigation }: Props) {
  const route = useRoute<any>();
  const { id } = route.params;
  const [item, setItem] = useState<Item | null>(null);
  const [loading, setLoading] = useState(true);

  useFocusEffect(
    useCallback(() => {
      fetchItem();
    }, [id])
  );

  const fetchItem = async () => {
    try {
      const res = await api.get(`/items/${id}`);
      setItem(res.data);
    } catch {
      Alert.alert('Error', 'Item not found');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = () => {
    Alert.alert(
      'Delete Item',
      'Are you sure you want to delete this item?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.delete(`/items/${id}`);
              Alert.alert('Deleted', 'Item has been deleted', [
                { text: 'OK', onPress: () => navigation.goBack() },
              ]);
            } catch {
              Alert.alert('Error', 'Failed to delete item');
            }
          },
        },
      ]
    );
  };

  const handleConsume = () => {
    navigation.navigate('ConsumeItem', { id });
  };

  if (loading) {
    return (
      <ActivityIndicator size="large" color="#8b5cf6" style={styles.loader} />
    );
  }

  if (!item) return null;

  const statusColor =
    item.status === 'active'
      ? '#22c55e'
      : item.status === 'expiring soon'
      ? '#f59e0b'
      : item.status === 'expired'
      ? '#ef4444'
      : '#6b7280';

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={[styles.status, { color: statusColor }]}>{item.status}</Text>
      </View>

      <View style={styles.card}>
        <Row label="Category" value={item.category} />
        <Row label="Owner" value={item.owner} />
        <Row label="Purchase Date" value={item.purchase_date} />
        <Row
          label="Quantity"
          value={`${item.quantity_value} ${item.quantity_unit}`}
        />
        <Row label="Location" value={item.location} />
        <Row
          label="Unopened Expiration"
          value={item.unopened_expiration_date}
        />
        <Row
          label="Opened Date"
          value={item.opened_date || '-'}
        />
        <Row
          label="Opened Expiration"
          value={item.opened_expiration_date || '-'}
        />
        <Row
          label="Current Expiration"
          value={item.current_expiration_date}
        />
        <Row label="Notes" value={item.notes || '-'} />
      </View>

      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.editBtn}
          onPress={() => navigation.navigate('EditItem', { id })}
        >
          <Text style={styles.editBtnText}>✏️ Edit</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.consumeBtn} onPress={handleConsume}>
          <Text style={styles.consumeBtnText}>✅ Consume</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.deleteBtn} onPress={handleDelete}>
          <Text style={styles.deleteBtnText}>🗑️ Delete</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={rowStyles.row}>
      <Text style={rowStyles.label}>{label}</Text>
      <Text style={rowStyles.value}>{value}</Text>
    </View>
  );
}

const rowStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  label: { fontSize: 14, color: '#6b7280', flex: 1 },
  value: { fontSize: 14, color: '#111827', flex: 1, textAlign: 'right', fontWeight: '500' },
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  loader: { flex: 1, justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  name: { fontSize: 22, fontWeight: 'bold', color: '#111827', flex: 1 },
  status: { fontSize: 14, fontWeight: 'bold', marginLeft: 8 },
  card: {
    backgroundColor: '#fff',
    margin: 16,
    padding: 16,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginHorizontal: 16,
    marginBottom: 30,
    gap: 8,
  },
  editBtn: {
    flex: 1,
    backgroundColor: '#3b82f6',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  editBtnText: { color: '#fff', fontWeight: 'bold' },
  consumeBtn: {
    flex: 1,
    backgroundColor: '#22c55e',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  consumeBtnText: { color: '#fff', fontWeight: 'bold' },
  deleteBtn: {
    flex: 1,
    backgroundColor: '#ef4444',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  deleteBtnText: { color: '#fff', fontWeight: 'bold' },
});
