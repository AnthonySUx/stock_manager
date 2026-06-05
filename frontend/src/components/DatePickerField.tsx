import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Platform,
  StyleSheet,
} from 'react-native';
import DateTimePicker, {
  DateTimePickerEvent,
} from '@react-native-community/datetimepicker';
import { neoInput, colors, spacing, radius } from '../theme';

interface DatePickerFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  allowPermanent?: boolean;
  canClear?: boolean;
  required?: boolean;
}

export default function DatePickerField({
  label,
  value,
  onChange,
  placeholder = '选择日期',
  allowPermanent = false,
  canClear = false,
  required = false,
}: DatePickerFieldProps) {
  const [expanded, setExpanded] = useState(false);

  const formatDate = (d: Date): string => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const parseDate = (dateStr: string): Date => {
    if (!dateStr || dateStr === '永久') return new Date();
    const parts = dateStr.split('-');
    return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  };

  const formatDisplayDate = (dateStr: string): string => {
    if (!dateStr || dateStr === '永久') return dateStr;
    const [y, m, d] = dateStr.split('-');
    return `${y}年${m}月${d}日`;
  };

  const handleDateChange = (_event: DateTimePickerEvent, selectedDate?: Date) => {
    if (Platform.OS === 'android') {
      setExpanded(false);
    }
    if (selectedDate) {
      onChange(formatDate(selectedDate));
    }
  };

  const handleDone = () => {
    if (!value) {
      const now = new Date();
      onChange(formatDate(now));
    }
    setExpanded(false);
  };

  const handleClear = () => {
    onChange('');
    setExpanded(false);
  };

  const handlePermanent = () => {
    onChange('永久');
    setExpanded(false);
  };

  const displayText = value ? (value === '永久' ? '永久' : formatDisplayDate(value)) : '';
  const isPermanent = value === '永久';

  return (
    <View style={styles.field}>
      <Text style={styles.label}>
        {label} {required && <Text style={styles.required}>*</Text>}
      </Text>

      <TouchableOpacity
        style={[styles.input, expanded && styles.inputExpanded]}
        activeOpacity={0.7}
        onPress={() => setExpanded(true)}
      >
        <Text
          style={[
            styles.inputText,
            !value && styles.placeholderText,
            isPermanent && styles.permanentText,
          ]}
        >
          {displayText || placeholder}
        </Text>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.pickerWrapper}>
          {Platform.OS === 'ios' ? (
            <>
              <DateTimePicker
                value={parseDate(value)}
                mode="date"
                display="spinner"
                onChange={handleDateChange}
                style={styles.inlinePicker}

                locale="zh-CN"
              />
              <View style={styles.actionRow}>
                {(canClear || value) && (
                  <TouchableOpacity onPress={handleClear} style={styles.actionBtn}>
                    <Text style={styles.actionBtnText}>清空</Text>
                  </TouchableOpacity>
                )}
                {allowPermanent && !isPermanent && (
                  <TouchableOpacity onPress={handlePermanent} style={styles.actionBtn}>
                    <Text style={styles.actionBtnText}>永久</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={handleDone} style={styles.doneBtn}>
                  <Text style={styles.doneBtnText}>完成</Text>
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <>
              <DateTimePicker
                value={parseDate(value)}
                mode="date"
                display="default"
                onChange={handleDateChange}
              />
              <View style={styles.actionRow}>
                {(canClear || value) && (
                  <TouchableOpacity onPress={handleClear} style={styles.actionBtn}>
                    <Text style={styles.actionBtnText}>清空</Text>
                  </TouchableOpacity>
                )}
                {allowPermanent && !isPermanent && (
                  <TouchableOpacity onPress={handlePermanent} style={styles.actionBtn}>
                    <Text style={styles.actionBtnText}>永久</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={handleDone} style={styles.doneBtn}>
                  <Text style={styles.doneBtnText}>完成</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    marginBottom: spacing.xl,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: spacing.xs + 1,
  },
  required: {
    color: colors.danger,
  },
  input: {
    ...neoInput,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  inputExpanded: {
    borderBottomLeftRadius: 0,
    borderBottomRightRadius: 0,
  },
  inputText: {
    fontSize: 15,
    color: colors.textPrimary,
  },
  placeholderText: {
    color: colors.textMuted,
  },
  permanentText: {
    color: colors.warning,
  },
  pickerWrapper: {
    backgroundColor: colors.bg,
    borderRadius: radius.md,
    paddingTop: spacing.sm,
    marginTop: -spacing.sm,
    paddingBottom: spacing.sm,
    alignItems: 'center',
  },
  inlinePicker: {
    height: 200,
    width: '100%',
  },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.xs,
    gap: spacing.sm,
  },
  actionBtn: {
    paddingVertical: spacing.sm - 2,
    paddingHorizontal: spacing.md,
    borderRadius: radius.full,
    backgroundColor: colors.chipBg,
    borderWidth: 0.5,
    borderColor: colors.surfaceBorder,
  },
  actionBtnText: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.textSecondary,
  },
  doneBtn: {
    paddingVertical: spacing.sm - 2,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.full,
    backgroundColor: colors.accent,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.24)',
  },
  doneBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.white,
  },
});
