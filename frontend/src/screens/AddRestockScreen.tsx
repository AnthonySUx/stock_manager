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
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="物品名称"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>分类</Text>
          <TextInput
            style={styles.input}
            value={category}
            onChangeText={setCategory}
            placeholder="例如 蔬菜、肉类"
          />
        </View>

        <View style={styles.fieldRow}>
          <View style={[styles.field, { flex: 1 }]}>
            <Text style={styles.label}>数量</Text>
            <TextInput
              style={styles.input}
              value={quantityValue}
              onChangeText={setQuantityValue}
              keyboardType="decimal-pad"
              placeholder="例如 1"
            />
          </View>
          <View style={[styles.field, { flex: 1, marginLeft: 8 }]}>
            <Text style={styles.label}>单位</Text>
            <TextInput
              style={styles.input}
              value={quantityUnit}
              onChangeText={setQuantityUnit}
              placeholder="例如 千克、个"
            />
          </View>
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>备注</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            value={notes}
            onChangeText={setNotes}
            placeholder="可选备注"
            multiline
          />
        </View>

        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          onPress={handleSave}
          disabled={saving}
        >
          <Text style={styles.saveBtnText}>
            {saving ? '保存中...' : '加入补货清单'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  content: { padding: 16, paddingBottom: 40 },
  title: { fontSize: 22, fontWeight: 'bold', color: '#111827', marginBottom: 16 },
  field: { marginBottom: 14 },
  fieldRow: { flexDirection: 'row', alignItems: 'flex-start' },
  label: { fontSize: 14, fontWeight: '600', color: '#374151', marginBottom: 4 },
  input: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: '#111827',
  },
  multiline: { minHeight: 60, textAlignVertical: 'top' },
  saveBtn: {
    backgroundColor: '#8b5cf6',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
});
