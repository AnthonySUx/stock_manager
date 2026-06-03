// Enhanced Soft Neumorphism design system — minimal, refined, accessible

export const colors = {
  // Core
  bg: '#eef1f5',
  surface: '#f4f8fd',
  surfaceBorder: 'rgba(255,255,255,0.7)',

  // Text
  textPrimary: '#1e293b',
  textSecondary: '#64748b',
  textMuted: '#94a3b8',

  // Accent (violet)
  accent: '#7c5cfc',
  accentLight: '#a78bfa',
  accentBg: '#ede9fe',

  // Semantic
  success: '#10b981',
  successLight: '#d1fae5',
  successBg: '#ecfdf5',

  warning: '#f59e0b',
  warningLight: '#fef3c7',
  warningBg: '#fffbeb',

  danger: '#ef4444',
  dangerLight: '#fde8e8',
  dangerBg: '#fef2f2',

  // Shadow system (soft neumorphism)
  shadowDark: '#cad1db',
  shadowDark2: '#bcc5d1',
  shadowLight: '#ffffff',
  shadowInset: '#dfe5ef',

  // Misc
  white: '#ffffff',
  chipBg: '#eef2f8',
  chipBorder: 'rgba(255,255,255,0.6)',
  inputBg: '#e8ecf4',
  inputBorder: '#d5dde8',
  overlay: 'rgba(0,0,0,0.04)',
  divider: 'rgba(0,0,0,0.06)',
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

// ─── Shadow Depth Layers ──────────────────────────────────────

// Extra small: for subtle chip / inline elements
export const shadowXs = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 2, height: 2 },
  shadowOpacity: 0.2,
  shadowRadius: 3,
  elevation: 1.5,
};

// Small: default raised card
export const shadowSm = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 4, height: 4 },
  shadowOpacity: 0.3,
  shadowRadius: 6,
  elevation: 3,
};

// Medium: elevated card or header
export const shadowMd = {
  shadowColor: colors.shadowDark2,
  shadowOffset: { width: 5, height: 5 },
  shadowOpacity: 0.35,
  shadowRadius: 8,
  elevation: 5,
};

// Large: FAB, modals
export const shadowLg = {
  shadowColor: colors.shadowDark2,
  shadowOffset: { width: 6, height: 6 },
  shadowOpacity: 0.4,
  shadowRadius: 10,
  elevation: 7,
};

// Extra large: prominent FAB
export const shadowXl = {
  shadowColor: colors.shadowDark2,
  shadowOffset: { width: 7, height: 7 },
  shadowOpacity: 0.45,
  shadowRadius: 12,
  elevation: 9,
};

// Inset shadow for inputs / pressed state
export const shadowInset = {
  shadowColor: colors.shadowInset,
  shadowOffset: { width: -2, height: -2 },
  shadowOpacity: 0.5,
  shadowRadius: 3,
  elevation: 1,
};

// ─── Common Style Presets ─────────────────────────────────────

// Raised card (standard)
export const neoCard = {
  backgroundColor: colors.surface,
  borderRadius: radius.md,
  borderWidth: 0.5,
  borderColor: colors.surfaceBorder,
  ...shadowSm,
};

// Elevated card (more prominence)
export const neoCardElevated = {
  backgroundColor: colors.surface,
  borderRadius: radius.lg,
  borderWidth: 0.5,
  borderColor: colors.surfaceBorder,
  ...shadowMd,
};

// Strong raised element (primary action)
export const neoButton = {
  backgroundColor: colors.accent,
  borderRadius: radius.md,
  borderWidth: 0.5,
  borderColor: 'rgba(255,255,255,0.35)',
  ...shadowMd,
};

// Inset / recessed (input field)
export const neoInput = {
  backgroundColor: colors.inputBg,
  borderRadius: radius.sm,
  borderWidth: 1,
  borderColor: colors.inputBorder,
  ...shadowInset,
};

// Filter chip
export const neoFilterChip = (active: boolean, activeColor?: string) => ({
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm - 2,
  borderRadius: radius.full,
  backgroundColor: active ? (activeColor || colors.accent) : colors.chipBg,
  borderWidth: 0.5,
  borderColor: active ? 'rgba(255,255,255,0.35)' : colors.surfaceBorder,
  ...(active ? { ...shadowXs, shadowColor: 'transparent' } : shadowXs),
});

// Status badge
export const neoBadge = (bgColor: string) => ({
  paddingHorizontal: spacing.sm + 2,
  paddingVertical: spacing.xs,
  borderRadius: radius.full,
  backgroundColor: bgColor,
  overflow: 'hidden' as const,
});

// ─── Typography ───────────────────────────────────────────────

export const typography = {
  h1: { fontSize: 22, fontWeight: '700' as const, color: colors.textPrimary },
  h2: { fontSize: 18, fontWeight: '700' as const, color: colors.textPrimary },
  h3: { fontSize: 16, fontWeight: '600' as const, color: colors.textPrimary },
  body: { fontSize: 15, color: colors.textPrimary },
  bodySmall: { fontSize: 13, color: colors.textSecondary },
  caption: { fontSize: 12, color: colors.textMuted },
};
