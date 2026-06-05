// Enhanced Soft Neumorphism design system — warm low-gloss variant
// Deep shadows + muted highlights for strong depth without eye strain
// Inspired by Emil Kowalski's design engineering philosophy

export const colors = {
  // Core — muted warm background
  bg: '#FDF1F0',
  surface: '#FDF1F0',
  surfaceBorder: 'rgba(255,255,255,0.40)',

  // Text
  textPrimary: '#4A3331',
  textSecondary: '#806B67',
  textMuted: '#9E8582',

  // Accent
  accent: '#FF6B57',
  accentLight: '#FF8A7A',
  accentBg: '#FFF0ED',

  // Semantic
  success: '#2ED573',
  successLight: '#D4EEDC',
  successBg: '#E6F5EC',

  warning: '#FFA502',
  warningLight: '#FFF0D0',
  warningBg: '#FFF8E6',

  danger: '#FF4757',
  dangerLight: '#F5D8DC',
  dangerBg: '#FFEAEC',

  // Shadow system
  shadowDark: '#E6D4D2',
  shadowDark2: '#E6D4D2',
  shadowLight: '#FFFFFF',
  shadowInset: '#E6D4D2',

  // Misc
  white: '#FFFFFF',
  chipBg: '#FDF1F0',
  chipBorder: 'rgba(255,255,255,0.40)',
  inputBg: '#FDF1F0',
  inputBorder: '#E6D4D2',
  overlay: 'rgba(0,0,0,0.04)',
  divider: 'rgba(0,0,0,0.06)',
};

export const status = {
  danger: '#FF4757',
  warning: '#FFA502',
  success: '#2ED573',
  expired: '#FF4757',
  expiringSoon: '#FFA502',
  active: '#2ED573',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 36,
  full: 999,
};

// ─── Shadow Depth Layers — ENHANCED ──────────────────────────
// Increased offset + radius + opacity for stronger neumorphism depth

export const shadowXs = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 3, height: 3 },
  shadowOpacity: 0.35,
  shadowRadius: 6,
  elevation: 3,
};

// Small: default raised card
export const shadowSm = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 6, height: 6 },
  shadowOpacity: 0.40,
  shadowRadius: 12,
  elevation: 5,
};

// Medium: elevated card or header
export const shadowMd = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 8, height: 8 },
  shadowOpacity: 0.45,
  shadowRadius: 18,
  elevation: 8,
};

// Large: FAB, modals
export const shadowLg = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 10, height: 10 },
  shadowOpacity: 0.48,
  shadowRadius: 22,
  elevation: 10,
};

// Extra large: prominent FAB
export const shadowXl = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 12, height: 12 },
  shadowOpacity: 0.50,
  shadowRadius: 26,
  elevation: 12,
};

// Inset shadow for inputs / pressed state — stronger recess
export const shadowInset = {
  shadowColor: colors.shadowInset,
  shadowOffset: { width: 3, height: 3 },
  shadowOpacity: 0.50,
  shadowRadius: 6,
  elevation: 2,
};

// ─── Dual-light edge helper ───────────────────────────────

export const lightEdge = (borderRadius: number = radius.xxl) => ({
  borderRadius,
  borderWidth: 0.5,
  borderColor: 'rgba(255,255,255,0.36)',
});

export const lightEdgeTop = (borderRadius: number = radius.xxl) => ({
  borderRadius,
  borderTopWidth: 1,
  borderLeftWidth: 1,
  borderColor: 'rgba(255,255,255,0.40)',
  borderRightWidth: 0,
  borderBottomWidth: 0,
});

// ─── Raised Neumorphism (凸起) ──────────────────────────
export const neuOut = {
  backgroundColor: colors.bg,
  borderRadius: radius.xxl,
  borderWidth: 0,
  ...shadowSm,
};

// ─── Inset Neumorphism (凹陷) ───────────────────────────
export const neuIn = {
  backgroundColor: colors.bg,
  borderRadius: radius.xxl,
  borderWidth: 0,
  ...shadowInset,
};

// ─── Warm Card (raised) ────────────────────────────────
export const neoCard = {
  backgroundColor: colors.bg,
  borderRadius: radius.xxl,
  borderWidth: 0,
  ...shadowSm,
};

export const neoCardElevated = {
  backgroundColor: colors.bg,
  borderRadius: radius.xxl,
  borderWidth: 0,
  ...shadowMd,
};

export const neoButton = {
  backgroundColor: colors.accent,
  borderRadius: radius.full,
  borderWidth: 0.5,
  borderColor: 'rgba(255,255,255,0.24)',
  ...shadowMd,
};

export const neoInput = {
  backgroundColor: colors.inputBg,
  borderRadius: radius.full,
  borderWidth: 0,
  ...shadowInset,
};

// Filter chip
export const neoFilterChip = (active: boolean, activeColor?: string) => ({
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm - 2,
  borderRadius: radius.full,
  backgroundColor: active ? (activeColor || colors.accent) : colors.chipBg,
  borderWidth: 0,
  ...(active ? {} : shadowXs),
});

// Status badge (mini pill)
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
