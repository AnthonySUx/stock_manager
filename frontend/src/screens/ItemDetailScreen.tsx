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
import { neoCard, neoBadge, colors, spacing, radius, shadowMd } from '../theme';

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
      ? '#10b981'
      : item.status === 'expiring soon'
      ? '#f59e0b'
      : item.status === 'expired'
      ? '#ef4444'
      : '#94a3b8';

  const statusBg =
    item.status === 'active'
      ? '#d1fae5'
      : item.status === 'expiring soon'
      ? '#fef3c7'
      : item.status === 'expired'
      ? '#fde8e8'
      : '#f1f5f9';

  const statusLabel =
    item.status === 'active' ? '有效'
    : item.status === 'expiring soon' ? '即将过期'
    : item.status === 'expired' ? '已过期'
    : item.status === 'consumed' ? '已消耗'
    : item.status;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.name}>{item.name}</Text>
        <View style={[styles.statusBadge, { backgroundColor: statusBg }]}>
          <Text style={[styles.status, { color: statusColor }]}>{statusLabel}</Text>
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
          activeOpacity={0.85}
          onPress={() => navigation.navigate('EditItem', { id })}
        >
          <Text style={styles.editBtnText}>✏️ 编辑</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.consumeBtn}
          activeOpacity={0.85}
          onPress={handleConsume}
        >
          <Text style={styles.consumeBtnText}>✅ 消耗</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.deleteBtn}
          activeOpacity={0.85}
          onPress={handleDelete}
        >
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
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
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
    backgroundColor: colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  name: { fontSize: 22, fontWeight: '700', color: colors.textPrimary, flex: 1 },
  status: { fontSize: 13, fontWeight: '700' },
  statusBadge: {
    paddingHorizontal: spacing.md - 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    marginLeft: spacing.sm,
  },
  card: {
    ...neoCard,
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
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  editBtnText: { color: colors.white, fontWeight: '700' },
  consumeBtn: {
    flex: 1,
    backgroundColor: '#10b981',
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    alignItems: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  consumeBtnText: { color: colors.white, fontWeight: '700' },
  deleteBtn: {
    flex: 1,
    backgroundColor: '#ef4444',
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    alignItems: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  deleteBtnText: { color: colors.white, fontWeight: '700' },
});
