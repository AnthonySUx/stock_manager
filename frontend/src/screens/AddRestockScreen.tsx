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
import { neoCard, neoInput, colors, spacing, radius, shadowMd } from '../theme';
import { PressableScale, NeoInsetField } from '../components/NeoComponents';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export default function AddRestockScreen({ navigation }: Props) {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [quantityValue, setQuantityValue] = useState('');
  const [quantityUnit, setQuantityUnit] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!name) {
      Alert.alert('错误', '名称为必填项');
      return;
    }

    setSaving(true);
    try {
      await api.post('/restock', {
        name,
        category: category || undefined,
        quantity_value: quantityValue ? parseFloat(quantityValue) : undefined,
        quantity_unit: quantityUnit || undefined,
        notes: notes || undefined,
      });
      Alert.alert('成功', '补货物品已添加', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('错误', err?.response?.data?.detail || '添加失败');
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
        <Text style={styles.title}>新增补货物品</Text>

        <View style={styles.field}>
          <Text style={styles.label}>名称 *</Text>
          <NeoInsetField
            value={name}
            onChangeText={setName}
            placeholder="物品名称"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>分类</Text>
          <NeoInsetField
            value={category}
            onChangeText={setCategory}
            placeholder="例如 蔬菜、肉类"
          />
        </View>

        <View style={styles.fieldRow}>
          <View style={[styles.field, { flex: 1 }]}>
            <Text style={styles.label}>数量</Text>
            <NeoInsetField
              value={quantityValue}
              onChangeText={setQuantityValue}
              keyboardType="decimal-pad"
              placeholder="例如 1"
            />
          </View>
          <View style={[styles.field, { flex: 1, marginLeft: spacing.sm }]}>
            <Text style={styles.label}>单位</Text>
            <NeoInsetField
              value={quantityUnit}
              onChangeText={setQuantityUnit}
              placeholder="例如 千克、个"
            />
          </View>
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>备注</Text>
          <NeoInsetField
            value={notes}
            onChangeText={setNotes}
            placeholder="可选备注"
            multiline
            numberOfLines={2}
          />
        </View>

        <PressableScale
          scaleIn={0.96}
          onPress={handleSave}
          disabled={saving}
        >
          <Text style={styles.saveBtnText}>
            {saving ? '保存中...' : '加入补货清单'}
          </Text>
        </PressableScale>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingBottom: 40 },
  title: { fontSize: 22, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.lg },
  field: { marginBottom: spacing.xl },
  fieldRow: { flexDirection: 'row', alignItems: 'flex-start' },
  label: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.xs + 1 },
  input: {
    ...neoInput,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  multiline: { minHeight: 60, textAlignVertical: 'top' },
  saveBtn: {
    backgroundColor: colors.accent,
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
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
});
