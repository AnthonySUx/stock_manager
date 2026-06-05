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
  Switch,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import api from '../api/client';
import type { Settings } from '../types';
import { neoCard, neoInput, colors, spacing, radius, shadowMd, neuOut, neuIn } from '../theme';
import { Ionicons } from '@expo/vector-icons';

export default function SettingsScreen() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [reminderDays, setReminderDays] = useState('');
  const [databasePath, setDatabasePath] = useState('');
  const [saving, setSaving] = useState(false);
  const [expiryReminderEnabled, setExpiryReminderEnabled] = useState(true);
  const [autoRestock, setAutoRestock] = useState(true);

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

  const insets = useSafeAreaInsets();

  if (loading) {
    return (
      <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
    );
  }

  return (
    <ScrollView style={styles.container}>
      {/* Header */}
      <View style={[styles.headerRow, { paddingTop: insets.top + spacing.sm }]}>
        <Text style={styles.screenTitle}>系统设置</Text>
      </View>

      {/* 偏好设置 */}
      <Text style={styles.sectionTitle}>偏好设置</Text>

      <View style={styles.settingsCard}>
        {/* 过期提醒通知 */}
        <View style={styles.settingsItem}>
          <View style={styles.settingsItemLeft}>
            <Ionicons name="notifications" size={18} color={colors.accent} style={styles.settingsIcon} />
            <Text style={styles.settingsLabel}>过期提醒通知</Text>
          </View>
          <TouchableOpacity
            style={[styles.toggle, expiryReminderEnabled ? styles.toggleOn : styles.toggleOff]}
            onPress={() => setExpiryReminderEnabled(!expiryReminderEnabled)}
            activeOpacity={0.7}
          >
            <View style={[styles.toggleKnob, expiryReminderEnabled ? styles.toggleKnobOn : styles.toggleKnobOff]} />
          </TouchableOpacity>
        </View>

        {/* 提前提醒天数 */}
        <View style={styles.settingsItem}>
          <View style={styles.settingsItemLeft}>
            <Ionicons name="calendar" size={18} color={colors.accent} style={styles.settingsIcon} />
            <Text style={styles.settingsLabel}>提前提醒天数</Text>
          </View>
          <View style={styles.settingsItemRight}>
            <TextInput
              style={styles.reminderDaysInput}
              value={reminderDays}
              onChangeText={setReminderDays}
              keyboardType="number-pad"
              placeholder="2"
              placeholderTextColor={colors.textMuted}
            />
            <Text style={styles.reminderDaysUnit}>天</Text>
            <Ionicons name="chevron-forward" size={14} color={colors.textMuted} style={{ marginLeft: 4 }} />
          </View>
        </View>

        {/* 自动加入补货清单 */}
        <View style={[styles.settingsItem, { borderBottomWidth: 0 }]}>
          <View style={styles.settingsItemLeft}>
            <Ionicons name="basket" size={18} color={colors.accent} style={styles.settingsIcon} />
            <Text style={styles.settingsLabel}>自动加入补货清单</Text>
          </View>
          <TouchableOpacity
            style={[styles.toggle, autoRestock ? styles.toggleOn : styles.toggleOff]}
            onPress={() => setAutoRestock(!autoRestock)}
            activeOpacity={0.7}
          >
            <View style={[styles.toggleKnob, autoRestock ? styles.toggleKnobOn : styles.toggleKnobOff]} />
          </TouchableOpacity>
        </View>
      </View>

      {/* 系统与数据 */}
      <Text style={styles.sectionTitle}>系统与数据</Text>

      <View style={styles.settingsCard}>
        {/* 数据源 */}
        <View style={styles.settingsItem}>
          <View style={styles.settingsItemLeft}>
            <Ionicons name="server" size={18} color={colors.accent} style={styles.settingsIcon} />
            <Text style={styles.settingsLabel}>数据源 (CLI)</Text>
          </View>
          <View style={styles.settingsItemRight}>
            <TextInput
              style={styles.databaseInput}
              value={databasePath}
              onChangeText={setDatabasePath}
              placeholder="MySQL"
              placeholderTextColor={colors.textMuted}
            />
            <Ionicons name="chevron-forward" size={14} color={colors.textMuted} style={{ marginLeft: 4 }} />
          </View>
        </View>

        {/* 保存按钮 */}
        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          activeOpacity={0.85}
          onPress={handleSave}
          disabled={saving}
        >
          <Ionicons name="checkmark" size={18} color="#ffffff" style={{ marginRight: 6 }} />
          <Text style={styles.saveBtnText}>
            {saving ? '保存中...' : '保存设置'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* 清理历史 */}
      <TouchableOpacity style={styles.clearBtn} activeOpacity={0.85}>
        <Ionicons name="trash" size={16} color={colors.danger} style={{ marginRight: 8 }} />
        <Text style={styles.clearBtnText}>清理已完成补货历史</Text>
      </TouchableOpacity>

      <View style={{ height: 120 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.sm,
    backgroundColor: colors.bg,
  },
  screenTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.textSecondary,
    marginHorizontal: spacing.xl,
    marginTop: spacing.xxl,
    marginBottom: spacing.md,
  },
  // Settings card (neumorphism raised)
  settingsCard: {
    marginHorizontal: spacing.xl,
    borderRadius: 30,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 6, height: 6 },
    shadowOpacity: 0.36,
    shadowRadius: 12,
    elevation: 4,
    paddingVertical: spacing.xs,
  },
  settingsItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  settingsItemLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  settingsIcon: {
    width: 28,
  },
  settingsLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  settingsItemRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  // Toggle switch
  toggle: {
    width: 50,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  toggleOn: {
    backgroundColor: colors.accent,
  },
  toggleOff: {
    backgroundColor: colors.textMuted,
  },
  toggleKnob: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: '#ffffff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.15,
    shadowRadius: 2,
    elevation: 2,
  },
  toggleKnobOn: {
    alignSelf: 'flex-end',
  },
  toggleKnobOff: {
    alignSelf: 'flex-start',
  },
  // Reminder days input
  reminderDaysInput: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.accent,
    textAlign: 'right',
    paddingVertical: 0,
    width: 30,
  },
  reminderDaysUnit: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.accent,
    marginLeft: 2,
  },
  // Database input
  databaseInput: {
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'right',
    paddingVertical: 0,
    minWidth: 80,
  },
  // Save button
  saveBtn: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginHorizontal: spacing.lg,
    marginVertical: spacing.lg,
    paddingVertical: spacing.md + 2,
    borderRadius: 26,
    backgroundColor: colors.accent,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: colors.white, fontSize: 15, fontWeight: '700' },
  // Clear button
  clearBtn: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginHorizontal: spacing.xl,
    marginTop: spacing.xxl,
    paddingVertical: spacing.lg,
    borderRadius: 30,
    backgroundColor: colors.bg,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 3,
  },
  clearBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.danger,
  },
});
