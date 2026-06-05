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
import { neoCard, colors, spacing, radius } from '../theme';
import { PressableScale } from '../components/NeoComponents';

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
      Alert.alert('错误', '加载提醒失败');
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
    const borderColor = isExpired ? '#ef4444' : '#f59e0b';
    const bgColor = isExpired ? '#fef2f2' : '#fffbeb';
    const label = isExpired ? '已过期' : '即将过期';

    return (
      <PressableScale
        scaleIn={0.97}
        onPress={() => navigation.navigate('ItemDetail', { id: item.id })}
        style={[styles.item, { backgroundColor: bgColor, borderLeftColor: borderColor }]}
      >
        <View style={styles.itemHeader}>
          <Text style={styles.itemName} numberOfLines={1}>{item.name}</Text>
          <View
            style={[
              styles.statusBadge,
              { backgroundColor: isExpired ? '#fde8e8' : '#fef3c7' },
            ]}
          >
            <Text
              style={[
                styles.statusBadgeText,
                { color: isExpired ? colors.danger : colors.warning },
              ]}
            >
              {label}
            </Text>
          </View>
        </View>
        <Text style={styles.itemDetail}>
          过期: {item.current_expiration_date}
        </Text>
        <Text style={styles.itemDetail}>
          {item.location} · {item.quantity_value} {item.quantity_unit}
        </Text>
      </PressableScale>
    );
  };

  if (loading) {
    return (
      <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
    );
  }

  return (
    <View style={styles.container}>
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
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>✅</Text>
            <Text style={styles.emptyTitle}>一切正常！</Text>
            <Text style={styles.emptySubtitle}>
              暂无即将过期或已过期的物品。
            </Text>
          </View>
        }
        contentContainerStyle={
          items.length === 0 ? styles.emptyFull : { paddingBottom: 20 }
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  item: {
    ...neoCard,
    marginHorizontal: spacing.lg - 2,
    marginTop: spacing.md,
    padding: spacing.lg,
    borderLeftWidth: 4,
  },
  statusBadge: {
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    overflow: 'hidden',
  },
  statusBadgeText: {
    fontSize: 12,
    fontWeight: '700',
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, flex: 1 },
  itemDetail: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.xs + 1 },
  emptyContainer: { alignItems: 'center', paddingTop: 60 },
  emptyFull: { flex: 1, justifyContent: 'center' },
  emptyIcon: { fontSize: 48, marginBottom: spacing.md },
  emptyTitle: { fontSize: 20, fontWeight: '700', color: colors.textPrimary },
  emptySubtitle: { fontSize: 14, color: colors.textSecondary, marginTop: spacing.xs },
});
