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
import { neoCard, neoInput, colors, spacing, radius, shadowMd } from '../theme';
import { PressableScale, NeoInsetField } from '../components/NeoComponents';
import DatePickerField from '../components/DatePickerField';

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
          <NeoInsetField
            value={purchasedQty}
            onChangeText={setPurchasedQty}
            keyboardType="decimal-pad"
            placeholder="数量"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>所有者</Text>
          <NeoInsetField
            value={owner}
            onChangeText={setOwner}
            placeholder="谁购买的？"
          />
        </View>

        <DatePickerField
          label="购买日期"
          value={purchaseDate}
          onChange={setPurchaseDate}
          placeholder="选择日期（默认今天）"
          canClear
        />

        <View style={styles.field}>
          <Text style={styles.label}>存放位置</Text>
          <NeoInsetField
            value={location}
            onChangeText={setLocation}
            placeholder="例如 冰箱"
          />
        </View>

        <DatePickerField
          label="过期日期（未开封）"
          value={unopenedExp}
          onChange={setUnopenedExp}
          placeholder="YYYY-MM-DD 或永久"
          allowPermanent
        />

        <DatePickerField
          label="开封日期（可选）"
          value={openedDate}
          onChange={setOpenedDate}
          placeholder="YYYY-MM-DD"
          canClear
        />

        <DatePickerField
          label="开封后过期日期（可选）"
          value={openedExp}
          onChange={setOpenedExp}
          placeholder="YYYY-MM-DD 或永久"
          allowPermanent
          canClear
        />

        <PressableScale
          scaleIn={0.96}
          onPress={handleDone}
          disabled={saving}
        >
          <Text style={styles.doneBtnText}>
            {saving ? '处理中...' : '✅ 加入库存并标记完成'}
          </Text>
        </PressableScale>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingBottom: 40 },
  title: { fontSize: 22, fontWeight: '700', color: colors.textPrimary },
  subtitle: { fontSize: 16, color: colors.textSecondary, marginBottom: spacing.xl, marginTop: spacing.xs },
  field: { marginBottom: spacing.xl },
  label: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.xs + 1 },
  input: {
    ...neoInput,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  doneBtn: {
    backgroundColor: '#10b981',
    paddingVertical: spacing.lg - 2,
    borderRadius: radius.full,
    alignItems: 'center',
    marginTop: spacing.sm,
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
  doneBtnDisabled: { opacity: 0.6 },
  doneBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
});
