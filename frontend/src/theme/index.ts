// Enhanced Soft Neumorphism design system — warm low-gloss variant
// Deep shadows + muted highlights for strong depth without eye strain
// Inspired by Emil Kowalski's design engineering philosophy

export const colors = {
  // Core — muted warm background
  bg: '#F2E2DF',
  surface: '#F2E2DF',
  surfaceBorder: 'rgba(255,255,255,0.30)',

  // Text
  textPrimary: '#442F2C',
  textSecondary: '#806B67',
  textMuted: '#A6928E',

  // Accent (柔和陶土橙)
  accent: '#DE705F',
  accentLight: '#E88A7A',
  accentBg: '#F7E4E0',

  // Semantic
  success: '#2DBD6F',
  successLight: '#D4EEDC',
  successBg: '#E6F5EC',

  warning: '#E8993E',
  warningLight: '#F7E8D0',
  warningBg: '#FBF3E6',

  danger: '#E84A58',
  dangerLight: '#F5D8DC',
  dangerBg: '#FBEAEC',

  // Shadow system (warm neumorphism) — DEEPER for strong depth
  shadowDark: '#C7AEA9',
  shadowDark2: '#BDA39E',
  shadowLight: '#FCF4F2',
  shadowInset: '#CDB8B4',

  // Misc
  white: '#FCF4F2',
  chipBg: '#EBD7D4',
  chipBorder: 'rgba(255,255,255,0.28)',
  inputBg: '#E9D7D4',
  inputBorder: '#DCC9C5',
  overlay: 'rgba(0,0,0,0.06)',
  divider: 'rgba(0,0,0,0.07)',
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
  xxl: 24,
  full: 999,
};

// ─── Shadow Depth Layers — ENHANCED ──────────────────────────
// Increased offset + radius + opacity for stronger neumorphism depth

// Extra small: chip, inline elements
export const shadowXs = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 2, height: 2 },
  shadowOpacity: 0.22,
  shadowRadius: 4,
  elevation: 2,
};

// Small: default raised card
export const shadowSm = {
  shadowColor: colors.shadowDark,
  shadowOffset: { width: 5, height: 5 },
  shadowOpacity: 0.36,
  shadowRadius: 12,
  elevation: 4,
};

// Medium: elevated card or header
export const shadowMd = {
  shadowColor: colors.shadowDark2,
  shadowOffset: { width: 7, height: 7 },
  shadowOpacity: 0.42,
  shadowRadius: 16,
  elevation: 6,
};

// Large: FAB, modals
export const shadowLg = {
  shadowColor: colors.shadowDark2,
  shadowOffset: { width: 9, height: 9 },
  shadowOpacity: 0.46,
  shadowRadius: 20,
  elevation: 8,
};

// Extra large: prominent FAB
export const shadowXl = {
  shadowColor: colors.shadowDark2,
  shadowOffset: { width: 10, height: 10 },
  shadowOpacity: 0.50,
  shadowRadius: 22,
  elevation: 10,
};

// Inset shadow for inputs / pressed state — stronger recess
export const shadowInset = {
  shadowColor: colors.shadowInset,
  shadowOffset: { width: -3, height: -3 },
  shadowOpacity: 0.55,
  shadowRadius: 6,
  elevation: 1.5,
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
