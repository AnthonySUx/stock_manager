// Neumorphism theme tokens and style helpers
export const colors = {
  bg: '#e8edf3',
  card: '#edf2f8',
  cardBorder: 'rgba(255,255,255,0.6)',
  textPrimary: '#2d4059',
  textSecondary: '#7b8b9e',
  textMuted: '#9aabb8',
  accent: '#8b5cf6',
  accentLight: '#a78bfa',
  success: '#2ecc71',
  successLight: '#d4f5e0',
  warning: '#f39c12',
  warningLight: '#fef3cd',
  danger: '#e74c3c',
  dangerLight: '#fde8e8',
  shadowDark: '#c0c8d6',
  shadowDark2: '#b8c2d4',
  shadowLight: '#ffffff',
  white: '#ffffff',
  chipBg: '#eef2f7',
  chipBorder: 'rgba(255,255,255,0.5)',
  inputBg: '#e4e9f0',
  inputBorder: '#d1d9e6',
  overlay: 'rgba(0,0,0,0.05)',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  full: 999,
};

// Raised neumorphic style for cards, buttons, chips (default state)
export const neoRaised = {
  backgroundColor: colors.card,
  borderRadius: radius.md,
  borderWidth: 0.5,
  borderColor: colors.cardBorder,
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 6, height: 6 },
  shadowOpacity: 0.4,
  shadowRadius: 8,
  elevation: 5,
};

// Strongly raised style (for FAB, primary action)
export const neoRaisedStrong = {
  backgroundColor: colors.accent,
  borderRadius: radius.md,
  shadowColor: colors.shadowDark2,
  shadowOffset: { width: 6, height: 6 },
  shadowOpacity: 0.5,
  shadowRadius: 10,
  elevation: 8,
};

// Recessed/inset style for inputs
export const neoInset = {
  backgroundColor: colors.inputBg,
  borderWidth: 1,
  borderColor: colors.inputBorder,
  borderRadius: radius.sm,
  shadowColor: colors.shadowLight,
  shadowOffset: { width: -2, height: -2 },
  shadowOpacity: 0.6,
  shadowRadius: 4,
  elevation: 1,
};

// Filter chip
export const neoChip = (active: boolean, activeColor?: string) => ({
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm - 2,
  borderRadius: radius.full,
  backgroundColor: active ? (activeColor || colors.accent) : colors.chipBg,
  borderWidth: 0.5,
  borderColor: active ? 'rgba(255,255,255,0.3)' : colors.cardBorder,
  shadowColor: active ? 'transparent' : colors.shadowDark,
  shadowOffset: { width: 3, height: 3 },
  shadowOpacity: 0.25,
  shadowRadius: 4,
  elevation: active ? 1 : 3,
});

// Status badge
export const statusBadge = (bgColor: string) => ({
  paddingHorizontal: spacing.sm + 2,
  paddingVertical: spacing.xs,
  borderRadius: radius.full,
  backgroundColor: bgColor,
  overflow: 'hidden' as const,
});
