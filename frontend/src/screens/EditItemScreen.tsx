import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
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
import type { Item } from '../types';

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

export default function EditItemScreen({ navigation }: Props) {
  const route = useRoute<any>();
  const { id } = route.params;
  const [item, setItem] = useState<Item | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [owner, setOwner] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [quantityValue, setQuantityValue] = useState('');
  const [quantityUnit, setQuantityUnit] = useState('');
  const [location, setLocation] = useState('');
  const [unopenedExp, setUnopenedExp] = useState('');
  const [openedExp, setOpenedExp] = useState('');
  const [openedDate, setOpenedDate] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    fetchItem();
  }, [id]);

  const fetchItem = async () => {
    try {
      const res = await api.get(`/items/${id}`);
      const i = res.data;
      setItem(i);
      setName(i.name);
      setCategory(i.category);
      setOwner(i.owner);
      setPurchaseDate(i.purchase_date);
      setQuantityValue(String(i.quantity_value));
      setQuantityUnit(i.quantity_unit);
      setLocation(i.location);
      setUnopenedExp(i.unopened_expiration_date);
      setOpenedExp(i.opened_expiration_date || '');
      setOpenedDate(i.opened_date || '');
      setNotes(i.notes || '');
    } catch {
      Alert.alert('错误', '加载物品失败');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.patch(`/items/${id}`, {
        name: name || undefined,
        category: category || undefined,
        owner: owner || undefined,
        purchase_date: purchaseDate || undefined,
        quantity_value: quantityValue ? parseFloat(quantityValue) : undefined,
        quantity_unit: quantityUnit || undefined,
        location: location || undefined,
        unopened_expiration_date: unopenedExp || undefined,
        opened_expiration_date: openedExp || null,
        opened_date: openedDate || null,
        notes: notes || null,
      });
      Alert.alert('已更新', '物品已更新', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('错误', err?.response?.data?.detail || '更新失败');
    } finally {
      setSaving(false);
    }
  };

  const renderChips = (
    options: string[],
    selected: string,
    onSelect: (v: string) => void,
  ) => (
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
  );

  if (loading) {
    return <ActivityIndicator size="large" color="#8b5cf6" style={styles.loader} />;
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>编辑物品</Text>

        <View style={styles.field}>
          <Text style={styles.label}>名称</Text>
          <TextInput style={styles.input} value={name} onChangeText={setName} />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>分类</Text>
          {renderChips(CATEGORIES, category, setCategory)}
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>所有者</Text>
          <TextInput style={styles.input} value={owner} onChangeText={setOwner} />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>购买日期</Text>
          <TextInput
            style={styles.input}
            value={purchaseDate}
            onChangeText={setPurchaseDate}
            placeholder="YYYY-MM-DD"
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
            />
          </View>
          <View style={[styles.field, { flex: 1, marginLeft: 8 }]}>
            <Text style={styles.label}>单位</Text>
            <TextInput
              style={styles.input}
              value={quantityUnit}
              onChangeText={setQuantityUnit}
            />
          </View>
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>存放位置</Text>
          {renderChips(LOCATIONS, location, setLocation)}
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>未开封过期日期</Text>
          <TextInput
            style={styles.input}
            value={unopenedExp}
            onChangeText={setUnopenedExp}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>开封日期</Text>
          <TextInput
            style={styles.input}
            value={openedDate}
            onChangeText={setOpenedDate}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>开封后过期日期</Text>
          <TextInput
            style={styles.input}
            value={openedExp}
            onChangeText={setOpenedExp}
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>备注</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            value={notes}
            onChangeText={setNotes}
            multiline
          />
        </View>

        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          onPress={handleSave}
          disabled={saving}
        >
          <Text style={styles.saveBtnText}>
            {saving ? '保存中...' : '保存修改'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  loader: { flex: 1, justifyContent: 'center' },
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
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f3f4f6',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  chipActive: { backgroundColor: '#8b5cf6', borderColor: '#8b5cf6' },
  chipText: { fontSize: 13, color: '#374151' },
  chipTextActive: { color: '#fff', fontWeight: 'bold' },
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
