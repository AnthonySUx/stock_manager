import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import type { Item } from '../types';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export default function ConsumeItemScreen({ navigation }: Props) {
  const route = useRoute<any>();
  const { id } = route.params;
  const [item, setItem] = useState<Item | null>(null);
  const [loading, setLoading] = useState(true);
  const [quantity, setQuantity] = useState('');
  const [addToRestock, setAddToRestock] = useState(false);
  const [consuming, setConsuming] = useState(false);

  useEffect(() => {
    fetchItem();
  }, [id]);

  const fetchItem = async () => {
    try {
      const res = await api.get(`/items/${id}`);
      setItem(res.data);
      setQuantity(String(res.data.quantity_value));
    } catch {
      Alert.alert('错误', '未找到物品');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  };

  const handleConsume = async () => {
    const qty = parseFloat(quantity);
    if (!qty || qty <= 0) {
      Alert.alert('错误', '请输入有效数量');
      return;
    }

    setConsuming(true);
    try {
      await api.post(`/items/${id}/consume`, {
        quantity: qty,
        add_to_restock: addToRestock,
      });
      Alert.alert('完成', '物品消耗成功', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('错误', err?.response?.data?.detail || '消耗失败');
    } finally {
      setConsuming(false);
    }
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#8b5cf6" style={styles.loader} />;
  }

  if (!item) return null;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.itemName}>{item.name}</Text>
        <Text style={styles.itemQty}>
          Current: {item.quantity_value} {item.quantity_unit}
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>消耗数量</Text>
        <TextInput
          style={styles.input}
          value={quantity}
          onChangeText={setQuantity}
          keyboardType="decimal-pad"
          placeholder="0"
        />

        <View style={styles.switchRow}>
          <Text style={styles.switchLabel}>清空时加入补货清单</Text>
          <Switch
            value={addToRestock}
            onValueChange={setAddToRestock}
            trackColor={{ false: '#d1d5db', true: '#c4b5fd' }}
            thumbColor={addToRestock ? '#8b5cf6' : '#f4f3f4'}
          />
        </View>

        <TouchableOpacity
          style={[styles.consumeBtn, consuming && styles.consumeBtnDisabled]}
          onPress={handleConsume}
          disabled={consuming}
        >
          <Text style={styles.consumeBtnText}>
            {consuming ? '消耗中...' : '✅ 消耗'}
          </Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  loader: { flex: 1, justifyContent: 'center' },
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
  itemName: { fontSize: 20, fontWeight: 'bold', color: '#111827' },
  itemQty: { fontSize: 15, color: '#6b7280', marginTop: 4 },
  label: { fontSize: 15, fontWeight: '600', color: '#374151', marginBottom: 8 },
  input: {
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 18,
    color: '#111827',
    textAlign: 'center',
  },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 16,
  },
  switchLabel: { fontSize: 14, color: '#374151', flex: 1, marginRight: 8 },
  consumeBtn: {
    backgroundColor: '#22c55e',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 16,
  },
  consumeBtnDisabled: { opacity: 0.6 },
  consumeBtnText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
});
