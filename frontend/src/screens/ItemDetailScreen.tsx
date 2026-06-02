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
      Alert.alert('错误', '未找到物品');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = () => {
    Alert.alert(
      '删除物品',
      '确定要删除此物品吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.delete(`/items/${id}`);
              Alert.alert('已删除', '物品已删除', [
                { text: '确定', onPress: () => navigation.goBack() },
              ]);
            } catch {
              Alert.alert('错误', '删除物品失败');
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
        <Row label="分类" value={item.category} />
        <Row label="所有者" value={item.owner} />
        <Row label="购买日期" value={item.purchase_date} />
        <Row
          label="数量"
          value={`${item.quantity_value} ${item.quantity_unit}`}
        />
        <Row label="存放位置" value={item.location} />
        <Row
          label="未开封过期日期"
          value={item.unopened_expiration_date}
        />
        <Row
          label="开封日期"
          value={item.opened_date || '-'}
        />
        <Row
          label="开封后过期日期"
          value={item.opened_expiration_date || '-'}
        />
        <Row
          label="当前过期日期"
          value={item.current_expiration_date}
        />
        <Row label="备注" value={item.notes || '-'} />
      </View>

      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.editBtn}
          onPress={() => navigation.navigate('EditItem', { id })}
        >
          <Text style={styles.editBtnText}>✏️ 编辑</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.consumeBtn} onPress={handleConsume}>
          <Text style={styles.consumeBtnText}>✅ 消耗</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.deleteBtn} onPress={handleDelete}>
          <Text style={styles.deleteBtnText}>🗑️ 删除</Text>
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
