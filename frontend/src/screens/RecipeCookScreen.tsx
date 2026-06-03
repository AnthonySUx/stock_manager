import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useRoute } from '@react-navigation/native';
import { recipesApi } from '../api/recipes';
import type { ConsumePreview, CookConsumedItem } from '../types';
import { neoCard, neoInput, colors, spacing, radius, shadowMd } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export default function RecipeCookScreen({ navigation }: Props) {
  const route = useRoute<any>();
  const { id, title: recipeTitle } = route.params;
  const [preview, setPreview] = useState<ConsumePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [cooking, setCooking] = useState(false);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [notes, setNotes] = useState('');
  const [result, setResult] = useState<{ consumed_items: CookConsumedItem[]; message: string } | null>(null);

  useEffect(() => {
    fetchPreview();
  }, [id]);

  const fetchPreview = async () => {
    try {
      const res = await recipesApi.consumePreview(id);
      setPreview(res.data);
      // Initialize quantities with suggested
      const initQ: Record<number, number> = {};
      res.data.suggestions.forEach((s) => {
        initQ[s.item_id] = s.suggested_quantity;
      });
      setQuantities(initQ);
    } catch {
      Alert.alert('错误', '获取消耗预览失败');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  };

  const updateQuantity = (itemId: number, value: string) => {
    const num = parseFloat(value);
    setQuantities((prev) => ({ ...prev, [itemId]: isNaN(num) ? 0 : num }));
  };

  const handleCook = async () => {
    const consume_items = Object.entries(quantities)
      .filter(([_, qty]) => qty > 0)
      .map(([itemId, quantity]) => ({
        item_id: parseInt(itemId, 10),
        quantity,
      }));

    if (consume_items.length === 0) {
      Alert.alert('提示', '请至少选择一种食材进行消耗');
      return;
    }

    setCooking(true);
    try {
      const res = await recipesApi.cook(id, {
        consume_items,
        notes: notes.trim() || null,
      });
      setResult({
        consumed_items: res.data.consumed_items,
        message: res.data.message,
      });
    } catch (err: any) {
      Alert.alert('错误', err?.response?.data?.detail || '烹饪记录失败');
    } finally {
      setCooking(false);
    }
  };

  if (loading) {
    return <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />;
  }

  if (result) {
    return (
      <ScrollView style={styles.container}>
        <View style={styles.resultCard}>
          <Ionicons name="checkmark-circle" size={64} color="#10b981" />
          <Text style={styles.resultTitle}>烹饪完成！</Text>
          <Text style={styles.resultMessage}>{result.message}</Text>
        </View>
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>消耗明细</Text>
          {result.consumed_items.map((item) => (
            <View key={item.item_id} style={styles.resultRow}>
              <Text style={styles.resultItemName}>{item.item_name}</Text>
              <Text style={styles.resultItemDetail}>
                消耗 {item.consumed_quantity} · 剩余 {item.remaining_quantity}
              </Text>
            </View>
          ))}
        </View>
        <TouchableOpacity
          style={styles.doneBtn}
          activeOpacity={0.85}
          onPress={() => navigation.goBack()}
        >
          <Text style={styles.doneBtnText}>完成</Text>
        </TouchableOpacity>
        <View style={{ height: 40 }} />
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.recipeTitle}>{recipeTitle}</Text>
        <Text style={styles.hint}>调整要消耗的食材数量，设为 0 可跳过</Text>
      </View>

      {/* Suggestions */}
      {preview && preview.suggestions.length > 0 ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>库存匹配</Text>
          {preview.suggestions.map((s) => (
            <View key={s.item_id} style={styles.suggestionRow}>
              <View style={styles.suggestionInfo}>
                <Text style={styles.suggestionName}>{s.ingredient_name}</Text>
                <Text style={styles.suggestionDetail}>
                  {s.item_name} · 可用: {s.available_quantity}
                  {s.status === 'expiring soon' && (
                    <Text style={{ color: '#f59e0b' }}> (临期)</Text>
                  )}
                </Text>
              </View>
              <TextInput
                style={styles.qtyInput}
                value={String(quantities[s.item_id] ?? 0)}
                onChangeText={(v) => updateQuantity(s.item_id, v)}
                keyboardType="decimal-pad"
                placeholder="0"
                placeholderTextColor={colors.textMuted}
              />
            </View>
          ))}
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.emptyHint}>未找到匹配的库存食材</Text>
        </View>
      )}

      {/* Unmatched */}
      {preview && preview.unmatched_ingredients.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>未匹配食材</Text>
          {preview.unmatched_ingredients.map((name, idx) => (
            <View key={idx} style={styles.unmatchedRow}>
              <Ionicons name="alert-circle-outline" size={16} color={colors.textMuted} />
              <Text style={styles.unmatchedText}>{name}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Notes */}
      <View style={styles.card}>
        <Text style={styles.label}>备注（可选）</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          value={notes}
          onChangeText={setNotes}
          placeholder="添加烹饪备注..."
          placeholderTextColor={colors.textMuted}
          multiline
          numberOfLines={2}
        />
      </View>

      {/* Cook Button */}
      <TouchableOpacity
        style={[styles.cookBtn, cooking && { opacity: 0.6 }]}
        activeOpacity={0.85}
        onPress={handleCook}
        disabled={cooking}
      >
        <Ionicons name="flame" size={20} color="#ffffff" />
        <Text style={styles.cookBtnText}>{cooking ? '烹饪中...' : '开始烹饪！'}</Text>
      </TouchableOpacity>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  card: {
    ...neoCard,
    margin: spacing.lg,
    marginBottom: 0,
    padding: spacing.lg,
  },
  recipeTitle: { fontSize: 20, fontWeight: '700', color: colors.textPrimary },
  hint: { fontSize: 14, color: colors.textSecondary, marginTop: spacing.xs },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.md },
  label: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.xs },
  input: {
    ...neoInput,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  multilineInput: { minHeight: 60, textAlignVertical: 'top' },
  suggestionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  suggestionInfo: { flex: 1 },
  suggestionName: { fontSize: 15, fontWeight: '600', color: colors.textPrimary },
  suggestionDetail: { fontSize: 13, color: colors.textSecondary, marginTop: 2 },
  qtyInput: {
    ...neoInput,
    width: 70,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm - 2,
    fontSize: 16,
    color: colors.textPrimary,
    textAlign: 'center',
  },
  unmatchedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  unmatchedText: { fontSize: 14, color: colors.textMuted },
  emptyHint: { fontSize: 15, color: colors.textMuted, textAlign: 'center' },
  cookBtn: {
    backgroundColor: '#f59e0b',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    paddingVertical: spacing.lg - 2,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  cookBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
  resultCard: {
    alignItems: 'center',
    padding: spacing.xxl,
    margin: spacing.lg,
    gap: spacing.md,
  },
  resultTitle: { fontSize: 22, fontWeight: '700', color: colors.textPrimary },
  resultMessage: { fontSize: 15, color: colors.textSecondary, textAlign: 'center' },
  resultRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  resultItemName: { fontSize: 15, fontWeight: '600', color: colors.textPrimary, flex: 1 },
  resultItemDetail: { fontSize: 13, color: colors.textSecondary },
  doneBtn: {
    backgroundColor: colors.accent,
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    paddingVertical: spacing.lg - 2,
    borderRadius: radius.md,
    alignItems: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  doneBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
});
