import React, { useCallback, useState } from 'react';
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
import { useFocusEffect } from '@react-navigation/native';
import api from '../api/client';
import type { Settings } from '../types';

export default function SettingsScreen() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [reminderDays, setReminderDays] = useState('');
  const [databasePath, setDatabasePath] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await api.get('/settings');
      setSettings(res.data);
      setReminderDays(res.data.expiration_reminder_days);
      setDatabasePath(res.data.default_database);
    } catch {
      Alert.alert('错误', '加载设置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      fetchSettings();
    }, [fetchSettings])
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.patch('/settings', {
        expiration_reminder_days: reminderDays || undefined,
        default_database: databasePath || undefined,
      });
      setSettings(res.data);
      Alert.alert('已保存', '设置更新成功');
    } catch (err: any) {
      Alert.alert('错误', err?.response?.data?.detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <ActivityIndicator size="large" color="#8b5cf6" style={styles.loader} />
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>设置</Text>

        <View style={styles.field}>
          <Text style={styles.label}>过期提醒天数</Text>
          <Text style={styles.hint}>
            过期前几天显示"即将过期"警告
          </Text>
          <TextInput
            style={styles.input}
            value={reminderDays}
            onChangeText={setReminderDays}
            keyboardType="number-pad"
            placeholder="2"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>默认数据库路径</Text>
          <Text style={styles.hint}>
            默认 SQLite 数据库路径（用于 CLI）
          </Text>
          <TextInput
            style={styles.input}
            value={databasePath}
            onChangeText={setDatabasePath}
            placeholder="stock.db"
          />
        </View>

        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          onPress={handleSave}
          disabled={saving}
        >
          <Text style={styles.saveBtnText}>
            {saving ? '保存中...' : '保存设置'}
          </Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  loader: { flex: 1, justifyContent: 'center' },
  card: {
    backgroundColor: '#fff',
    margin: 16,
    padding: 16,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  title: { fontSize: 22, fontWeight: 'bold', color: '#111827', marginBottom: 16 },
  field: { marginBottom: 18 },
  label: { fontSize: 15, fontWeight: '600', color: '#374151', marginBottom: 2 },
  hint: { fontSize: 12, color: '#9ca3af', marginBottom: 6 },
  input: {
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: '#111827',
  },
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
