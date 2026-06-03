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
import { neoCard, neoInput, colors, spacing, radius, shadowMd } from '../theme';

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
    return <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />;
  }

  if (!item) return null;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.itemName}>{item.name}</Text>
        <Text style={styles.itemQty}>
          当前库存: {item.quantity_value} {item.quantity_unit}
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
          placeholderTextColor={colors.textMuted}
        />

        <View style={styles.switchRow}>
          <Text style={styles.switchLabel}>清空时加入补货清单</Text>
          <Switch
            value={addToRestock}
            onValueChange={setAddToRestock}
            trackColor={{ false: '#d5dde8', true: '#c4b5fd' }}
            thumbColor={addToRestock ? colors.accent : '#f4f3f4'}
          />
        </View>

        <TouchableOpacity
          style={[styles.consumeBtn, consuming && styles.consumeBtnDisabled]}
          activeOpacity={0.85}
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
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  card: {
    ...neoCard,
    margin: spacing.lg,
    padding: spacing.lg,
  },
  itemName: { fontSize: 20, fontWeight: '700', color: colors.textPrimary },
  itemQty: { fontSize: 15, color: colors.textSecondary, marginTop: spacing.xs },
  label: { fontSize: 15, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.sm },
  input: {
    ...neoInput,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 18,
    color: colors.textPrimary,
    textAlign: 'center',
  },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.xl,
  },
  switchLabel: { fontSize: 14, color: colors.textPrimary, flex: 1, marginRight: spacing.sm },
  consumeBtn: {
    backgroundColor: '#10b981',
    paddingVertical: spacing.lg - 2,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.xl,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  consumeBtnDisabled: { opacity: 0.6 },
  consumeBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
});
