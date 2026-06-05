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
import { neoCard, neoFilterChip, colors, spacing, radius, shadowMd, shadowXl } from '../theme';
import { PressableScale } from '../components/NeoComponents';

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
      Alert.alert('错误', '加载补货物品失败');
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
    Alert.alert('删除', `确定从补货清单中删除"${item.name}"吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await api.delete(`/restock/${item.id}`);
            fetchItems(filter);
          } catch {
            Alert.alert('错误', '删除失败');
          }
        },
      },
    ]);
  };

  const renderItem = ({ item }: { item: RestockItem }) => (
    <View style={styles.item}>
      <View style={styles.itemHeader}>
        <Text style={styles.itemName} numberOfLines={1}>{item.name}</Text>
        <View
          style={[
            styles.statusBadge,
            { backgroundColor: item.status === 'pending' ? '#fef3c7' : '#d1fae5' },
          ]}
        >
          <Text
            style={[
              styles.itemStatus,
              { color: item.status === 'pending' ? '#f59e0b' : '#10b981' },
            ]}
          >
            {item.status === 'pending' ? '待补货' : item.status === 'done' ? '已完成' : item.status}
          </Text>
        </View>
      </View>
      {item.category && (
        <Text style={styles.itemDetail}>{item.category}</Text>
      )}
      <Text style={styles.itemDetail}>数量: {formatQuantity(item)}</Text>
      {item.status === 'pending' && (
        <View style={styles.itemActions}>
          <PressableScale
            scaleIn={0.96}
            onPress={() => handleDone(item)}
            style={styles.doneBtn}
          >
            <Text style={styles.doneBtnText}>✅ 完成</Text>
          </PressableScale>
          <PressableScale
            scaleIn={0.92}
            onPress={() => handleDelete(item)}
            style={styles.deleteSmallBtn}
          >
            <Text style={styles.deleteSmallBtnText}>🗑️</Text>
          </PressableScale>
        </View>
      )}
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.filterRow}>
        {[
          { label: '待补货', value: 'pending' },
          { label: '已完成', value: 'done' },
          { label: '全部', value: null },
        ].map((f) => (
          <TouchableOpacity
            key={f.label}
            style={neoFilterChip(filter === f.value)}
            activeOpacity={0.7}
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
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={colors.textMuted}
              colors={[colors.accent]}
            />
          }
          ListEmptyComponent={
            <Text style={styles.empty}>暂无补货物品</Text>
          }
          contentContainerStyle={
            items.length === 0 ? styles.emptyContainer : { paddingBottom: 80 }
          }
        />
      )}

      <PressableScale
        scaleIn={0.94}
        onPress={() => navigation.navigate('AddRestock')}
        style={styles.fab}
      >
        <Text style={styles.fabText}>+</Text>
      </PressableScale>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.md,
    gap: spacing.sm - 2,
    backgroundColor: colors.bg,
  },
  filterChipText: { fontSize: 13, color: colors.textSecondary },
  filterChipTextActive: { color: colors.white, fontWeight: '600' },
  item: {
    marginHorizontal: spacing.lg - 2,
    marginTop: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.xxl,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark2,
    shadowOffset: { width: 5, height: 5 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 4,
    borderTopWidth: 0.5,
    borderLeftWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.36)',
    borderRightWidth: 0,
    borderBottomWidth: 0,
  },
  statusBadge: {
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    overflow: 'hidden',
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, flex: 1 },
  itemStatus: { fontSize: 12, fontWeight: '700' },
  itemDetail: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.xs + 1 },
  itemActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  doneBtn: {
    backgroundColor: '#10b981',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    borderTopWidth: 0.5,
    borderLeftWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.24)',
    borderRightWidth: 0,
    borderBottomWidth: 0,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  doneBtnText: { color: colors.white, fontWeight: '700', fontSize: 14 },
  deleteSmallBtn: {
    padding: spacing.sm,
  },
  deleteSmallBtnText: { fontSize: 18 },
  empty: { fontSize: 16, color: colors.textMuted, textAlign: 'center' },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  fab: {
    position: 'absolute',
    right: spacing.xl,
    bottom: 110,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.accent,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    borderTopWidth: 0.5,
    borderLeftWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.24)',
    borderRightWidth: 0,
    borderBottomWidth: 0,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 12,
    elevation: 7,
  },
  fabText: { fontSize: 28, color: colors.white, lineHeight: 30, marginTop: -1 },
});
