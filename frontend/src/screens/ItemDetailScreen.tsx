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
import { neoRaised, colors, spacing, radius } from '../theme';

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
      <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
    );
  }

  if (!item) return null;

  const statusColor =
    item.status === 'active'
      ? '#2ecc71'
      : item.status === 'expiring soon'
      ? '#f39c12'
      : item.status === 'expired'
      ? '#e74c3c'
      : '#95a5a6';

  const statusBg =
    item.status === 'active'
      ? '#d4f5e0'
      : item.status === 'expiring soon'
      ? '#fef3cd'
      : item.status === 'expired'
      ? '#fde8e8'
      : '#f0f0f0';

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.name}>{item.name}</Text>
        <View style={[styles.statusBadge, { backgroundColor: statusBg }]}>
          <Text style={[styles.status, { color: statusColor }]}>{item.status}</Text>
        </View>
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
    paddingVertical: spacing.md - 2,
    borderBottomWidth: 0.5,
    borderBottomColor: 'rgba(0,0,0,0.05)',
  },
  label: { fontSize: 14, color: colors.textSecondary, flex: 1 },
  value: { fontSize: 14, color: colors.textPrimary, flex: 1, textAlign: 'right', fontWeight: '500' },
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.lg,
    backgroundColor: colors.card,
    borderBottomWidth: 0.5,
    borderBottomColor: 'rgba(0,0,0,0.05)',
  },
  name: { fontSize: 22, fontWeight: 'bold', color: colors.textPrimary, flex: 1 },
  status: { fontSize: 13, fontWeight: 'bold' },
  statusBadge: {
    paddingHorizontal: spacing.md - 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    marginLeft: spacing.sm,
  },
  card: {
    ...neoRaised,
    margin: spacing.lg,
    padding: spacing.lg,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginHorizontal: spacing.lg,
    marginBottom: 30,
    gap: spacing.sm,
  },
  editBtn: {
    flex: 1,
    backgroundColor: '#3b82f6',
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    alignItems: 'center',
    shadowColor: colors.shadowDark2,
    shadowOffset: { width: 3, height: 3 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 4,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  editBtnText: { color: colors.white, fontWeight: 'bold' },
  consumeBtn: {
    flex: 1,
    backgroundColor: '#2ecc71',
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    alignItems: 'center',
    shadowColor: colors.shadowDark2,
    shadowOffset: { width: 3, height: 3 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 4,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  consumeBtnText: { color: colors.white, fontWeight: 'bold' },
  deleteBtn: {
    flex: 1,
    backgroundColor: '#e74c3c',
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    alignItems: 'center',
    shadowColor: colors.shadowDark2,
    shadowOffset: { width: 3, height: 3 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 4,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  deleteBtnText: { color: colors.white, fontWeight: 'bold' },
});
