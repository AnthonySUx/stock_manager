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
import { neoCard, neoInput, colors, spacing, radius, shadowMd } from '../theme';

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
      <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
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
            placeholderTextColor={colors.textMuted}
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
            placeholderTextColor={colors.textMuted}
          />
        </View>

        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          activeOpacity={0.85}
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
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  card: {
    ...neoCard,
    margin: spacing.lg,
    padding: spacing.lg,
  },
  title: { fontSize: 22, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.lg },
  field: { marginBottom: spacing.xl },
  label: { fontSize: 15, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.xs },
  hint: { fontSize: 12, color: colors.textMuted, marginBottom: spacing.sm },
  input: {
    ...neoInput,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  saveBtn: {
    ...neoCard,
    backgroundColor: colors.accent,
    paddingVertical: spacing.lg - 2,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.sm,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
});
