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
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import api from '../api/client';
import { neoRaised, neoInset, neoChip, colors, spacing, radius } from '../theme';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const CATEGORIES = [
  '蔬菜', '肉类', '水果', '药品', '冷冻食品', '宠物食品',
  '乳制品', '饮料', '调味品', '零食', '谷物', '其他',
];

const LOCATIONS = [
  '冰箱', '冷冻室', '储物柜', '食品储藏室', '柜台', '其他',
];

const UNITS = ['个', '克', '千克', '毫升', '升', '袋', '瓶', '盒', '罐', '包'];

export default function AddItemScreen({ navigation }: Props) {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [owner, setOwner] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [quantityValue, setQuantityValue] = useState('');
  const [quantityUnit, setQuantityUnit] = useState('个');
  const [location, setLocation] = useState('');
  const [unopenedExp, setUnopenedExp] = useState('');
  const [openedExp, setOpenedExp] = useState('');
  const [openedDate, setOpenedDate] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!name || !category || !owner || !quantityValue || !location || !unopenedExp) {
      Alert.alert('错误', '请填写所有必填字段');
      return;
    }

    const currentExp = openedDate && openedExp ? openedExp : unopenedExp;

    setSaving(true);
    try {
      await api.post('/items', {
        name,
        category,
        owner,
        purchase_date: purchaseDate || new Date().toISOString().split('T')[0],
        quantity_value: parseFloat(quantityValue),
        quantity_unit: quantityUnit,
        location,
        unopened_expiration_date: unopenedExp,
        opened_expiration_date: openedExp || null,
        opened_date: openedDate || null,
        current_expiration_date: currentExp,
        notes: notes || null,
      });
      Alert.alert('成功', '物品已添加', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('错误', err?.response?.data?.detail || '添加物品失败');
    } finally {
      setSaving(false);
    }
  };

  const renderChips = (
    label: string,
    options: string[],
    selected: string,
    onSelect: (v: string) => void,
    required?: boolean
  ) => (
    <View style={styles.field}>
      <Text style={styles.label}>
        {label} {required && <Text style={styles.required}>*</Text>}
      </Text>
      <View style={styles.chipRow}>
        {options.map((opt) => (
          <TouchableOpacity
            key={opt}
            style={[styles.chip, selected === opt && styles.chipActive]}
            onPress={() => onSelect(opt)}
          >
            <Text style={[styles.chipText, selected === opt && styles.chipTextActive]}>
              {opt}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );

  const renderUnitChip = (opt: string) => (
    <TouchableOpacity
      key={opt}
      style={[styles.chip, quantityUnit === opt && styles.chipActive]}
      onPress={() => setQuantityUnit(opt)}
    >
      <Text style={[styles.chipText, quantityUnit === opt && styles.chipTextActive]}>
        {opt}
      </Text>
    </TouchableOpacity>
  );

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>新增库存物品</Text>

        {/* Name */}
        <View style={styles.field}>
          <Text style={styles.label}>名称 *</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="物品名称"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        {/* Category */}
        {renderChips('分类', CATEGORIES, category, setCategory, true)}

        {/* Owner */}
        <View style={styles.field}>
          <Text style={styles.label}>所有者 *</Text>
          <TextInput
            style={styles.input}
            value={owner}
            onChangeText={setOwner}
            placeholder="谁购买的？"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        {/* Purchase Date */}
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

        {/* Quantity */}
        <View style={styles.fieldRow}>
          <View style={[styles.field, { flex: 1 }]}>
            <Text style={styles.label}>数量 *</Text>
            <TextInput
              style={styles.input}
              value={quantityValue}
              onChangeText={setQuantityValue}
              placeholder="例如 2"
              placeholderTextColor={colors.textMuted}
              keyboardType="decimal-pad"
            />
          </View>
          <View style={[styles.field, { flex: 1, marginLeft: spacing.sm }]}>
            <Text style={styles.label}>单位</Text>
            <View style={styles.chipRow}>
              {UNITS.map(renderUnitChip)}
            </View>
          </View>
        </View>

        {/* Location */}
        {renderChips('存放位置', LOCATIONS, location, setLocation, true)}

        {/* Expiration Dates */}
        <View style={styles.field}>
          <Text style={styles.label}>未开封过期日期 *</Text>
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
            placeholder="YYYY-MM-DD 或永久"
            placeholderTextColor={colors.textMuted}
          />
        </View>

        {/* Notes */}
        <View style={styles.field}>
          <Text style={styles.label}>备注</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            value={notes}
            onChangeText={setNotes}
            placeholder="可选备注"
            placeholderTextColor={colors.textMuted}
            multiline
          />
        </View>

        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          onPress={handleSave}
          disabled={saving}
        >
          <Text style={styles.saveBtnText}>
            {saving ? '保存中...' : '保存物品'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingBottom: 40 },
  title: { fontSize: 22, fontWeight: 'bold', color: colors.textPrimary, marginBottom: spacing.lg },
  field: { marginBottom: spacing.lg - 2 },
  fieldRow: { flexDirection: 'row', alignItems: 'flex-start' },
  label: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.xs + 1 },
  required: { color: colors.danger },
  input: {
    ...neoInset,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  multiline: { minHeight: 60, textAlignVertical: 'top' },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm - 2,
  },
  chip: {
    ...neoChip(false),
  },
  chipActive: {
    ...neoChip(true),
  },
  chipText: { fontSize: 13, color: colors.textSecondary },
  chipTextActive: { color: colors.white, fontWeight: 'bold' },
  saveBtn: {
    backgroundColor: colors.accent,
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
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: colors.white, fontSize: 16, fontWeight: 'bold' },
});
