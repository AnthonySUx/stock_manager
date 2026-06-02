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

const CATEGORIES = [
  'vegetable', 'meat', 'fruit', 'medicine', 'frozen food', 'pet food',
  'dairy', 'beverage', 'condiment', 'snack', 'grain', 'other',
];

const LOCATIONS = [
  'refrigerator', 'freezer', 'storage cabinet', 'pantry', 'counter', 'other',
];

const UNITS = ['pcs', 'g', 'kg', 'ml', 'l', 'bags', 'bottles', 'boxes', 'cans', 'pack'];

export default function AddItemScreen({ navigation }: Props) {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [owner, setOwner] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [quantityValue, setQuantityValue] = useState('');
  const [quantityUnit, setQuantityUnit] = useState('pcs');
  const [location, setLocation] = useState('');
  const [unopenedExp, setUnopenedExp] = useState('');
  const [openedExp, setOpenedExp] = useState('');
  const [openedDate, setOpenedDate] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!name || !category || !owner || !quantityValue || !location || !unopenedExp) {
      Alert.alert('Error', 'Please fill all required fields');
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
      Alert.alert('Success', 'Item added', [
        { text: 'OK', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('Error', err?.response?.data?.detail || 'Failed to add item');
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

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Add Stock Item</Text>

        {/* Name */}
        <View style={styles.field}>
          <Text style={styles.label}>Name *</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="Item name"
          />
        </View>

        {/* Category */}
        {renderChips('Category', CATEGORIES, category, setCategory, true)}

        {/* Owner */}
        <View style={styles.field}>
          <Text style={styles.label}>Owner *</Text>
          <TextInput
            style={styles.input}
            value={owner}
            onChangeText={setOwner}
            placeholder="Who bought this?"
          />
        </View>

        {/* Purchase Date */}
        <View style={styles.field}>
          <Text style={styles.label}>Purchase Date</Text>
          <TextInput
            style={styles.input}
            value={purchaseDate}
            onChangeText={setPurchaseDate}
            placeholder="YYYY-MM-DD (default: today)"
          />
        </View>

        {/* Quantity */}
        <View style={styles.fieldRow}>
          <View style={[styles.field, { flex: 1 }]}>
            <Text style={styles.label}>Quantity *</Text>
            <TextInput
              style={styles.input}
              value={quantityValue}
              onChangeText={setQuantityValue}
              placeholder="e.g. 2"
              keyboardType="decimal-pad"
            />
          </View>
          <View style={[styles.field, { flex: 1, marginLeft: 8 }]}>
            <Text style={styles.label}>Unit</Text>
            <View style={styles.chipRow}>
              {UNITS.map((opt) => (
                <TouchableOpacity
                  key={opt}
                  style={[styles.chip, quantityUnit === opt && styles.chipActive]}
                  onPress={() => setQuantityUnit(opt)}
                >
                  <Text style={[styles.chipText, quantityUnit === opt && styles.chipTextActive]}>
                    {opt}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </View>

        {/* Location */}
        {renderChips('Location', LOCATIONS, location, setLocation, true)}

        {/* Expiration Dates */}
        <View style={styles.field}>
          <Text style={styles.label}>Unopened Expiration Date *</Text>
          <TextInput
            style={styles.input}
            value={unopenedExp}
            onChangeText={setUnopenedExp}
            placeholder="YYYY-MM-DD or infinite"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>Opened Date (optional)</Text>
          <TextInput
            style={styles.input}
            value={openedDate}
            onChangeText={setOpenedDate}
            placeholder="YYYY-MM-DD"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>Opened Expiration (optional)</Text>
          <TextInput
            style={styles.input}
            value={openedExp}
            onChangeText={setOpenedExp}
            placeholder="YYYY-MM-DD or infinite"
          />
        </View>

        {/* Notes */}
        <View style={styles.field}>
          <Text style={styles.label}>Notes</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            value={notes}
            onChangeText={setNotes}
            placeholder="Optional notes"
            multiline
          />
        </View>

        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          onPress={handleSave}
          disabled={saving}
        >
          <Text style={styles.saveBtnText}>
            {saving ? 'Saving...' : 'Save Item'}
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
  required: { color: '#ef4444' },
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
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f3f4f6',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  chipActive: {
    backgroundColor: '#8b5cf6',
    borderColor: '#8b5cf6',
  },
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
