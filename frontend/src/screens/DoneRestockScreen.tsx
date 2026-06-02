import React, { useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import type { RestockItem } from '../types';
import { neoRaised, neoInset, colors, spacing, radius } from '../theme';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export default function DoneRestockScreen({ navigation }: Props) {
  const route = useRoute<any>();
  const { id, item: restockItem } = route.params as {
    id: number;
    item: RestockItem;
  };

  const [purchasedQty, setPurchasedQty] = useState(
    String(restockItem.quantity_value || '')
  );
  const [owner, setOwner] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [location, setLocation] = useState('');
  const [unopenedExp, setUnopenedExp] = useState('');
  const [openedExp, setOpenedExp] = useState('');
  const [openedDate, setOpenedDate] = useState('');
  const [saving, setSaving] = useState(false);

  const handleDone = async () => {
    if (!purchasedQty || parseFloat(purchasedQty) <= 0) {
      Alert.alert('错误', '请输入有效购买数量');
      return;
    }

    setSaving(true);
    try {
      await api.post(`/restock/${id}/done`, {
        purchased_quantity: parseFloat(purchasedQty),
        owner: owner || undefined,
        purchase_date: purchaseDate || undefined,
        location: location || undefined,
        unopened_expiration_date: unopenedExp || undefined,
        opened_expiration_date: openedExp || null,
        opened_date: openedDate || null,
      });
      Alert.alert('完成', '物品已加入库存', [
        { text: '确定', onPress: () => navigation.navigate('RestockList') },
      ]);
    } catch (err: any) {
      Alert.alert('错误', err?.response?.data?.detail || '处理失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>完成补货</Text>
        <Text style={styles.subtitle}>{restockItem.name}</Text>

        <View style={styles.field}>
          <Text style={styles.label}>购买数量 *</Text>
          <TextInput
            style={styles.input}
            value={purchasedQty}
            onChangeText={setPurchasedQty}
            keyboardType="decimal-pad"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>所有者</Text>
          <TextInput
            style={styles.input}
            value={owner}
            onChangeText={setOwner}
            placeholder="谁购买的？"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>购买日期</Text>
          <TextInput
            style={styles.input}
            value={purchaseDate}
            onChangeText={setPurchaseDate}
            placeholder="YYYY-MM-DD（默认今天）"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>存放位置</Text>
          <TextInput
            style={styles.input}
            value={location}
            onChangeText={setLocation}
            placeholder="例如 冰箱"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>过期日期（未开封）</Text>
          <TextInput
            style={styles.input}
            value={unopenedExp}
            onChangeText={setUnopenedExp}
            placeholder="YYYY-MM-DD 或永久"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>开封日期（可选）</Text>
          <TextInput
            style={styles.input}
            value={openedDate}
            onChangeText={setOpenedDate}
            placeholder="YYYY-MM-DD"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>开封后过期日期（可选）</Text>
          <TextInput
            style={styles.input}
            value={openedExp}
            onChangeText={setOpenedExp}
            placeholder="YYYY-MM-DD"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <TouchableOpacity
          style={[styles.doneBtn, saving && styles.doneBtnDisabled]}
          onPress={handleDone}
          disabled={saving}
        >
          <Text style={styles.doneBtnText}>
            {saving ? '处理中...' : '✅ 加入库存并标记完成'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingBottom: 40 },
  title: { fontSize: 22, fontWeight: 'bold', color: colors.textPrimary },
  subtitle: { fontSize: 16, color: colors.textSecondary, marginBottom: spacing.lg, marginTop: spacing.xs },
  field: { marginBottom: spacing.lg - 2 },
  label: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.xs + 1 },
  input: {
    ...neoInset,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  doneBtn: {
    backgroundColor: '#2ecc71',
    paddingVertical: spacing.lg - 2,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.sm,
    shadowColor: colors.shadowDark2,
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 6,
    elevation: 5,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  doneBtnDisabled: { opacity: 0.6 },
  doneBtnText: { color: colors.white, fontSize: 16, fontWeight: 'bold' },
});
