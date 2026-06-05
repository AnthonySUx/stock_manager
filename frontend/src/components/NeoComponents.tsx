// NeoComponents — Reusable Neumorphism primitives
// Built with Emil Kowalski's philosophy: touch should feel physical

import React, { useCallback, useRef, useState } from 'react';
import {
    Animated,
    Pressable,
    View,
    Text,
    TextInput,
    StyleSheet,
    type ViewStyle,
    type TextStyle,
    type StyleProp,
    type PressableProps,
} from 'react-native';
import { Canvas, RoundedRect, Shadow } from '@shopify/react-native-skia';
import { colors, radius, spacing } from '../theme';

// ─── PressableScale ─────────────────────────────────────────

interface PressableScaleProps extends PressableProps {
    children: React.ReactNode;
    scaleIn?: number;
    style?: StyleProp<ViewStyle>;
}

export function PressableScale({
    children,
    scaleIn = 0.97,
    style,
    onPressIn,
    onPressOut,
    ...rest
}: PressableScaleProps) {
    const scaleAnim = useRef(new Animated.Value(1)).current;

    const handlePressIn = useCallback(
        (e: any) => {
            Animated.spring(scaleAnim, {
                toValue: scaleIn,
                useNativeDriver: true,
                stiffness: 300,
                damping: 18,
            }).start();
            onPressIn?.(e);
        },
        [scaleIn, scaleAnim, onPressIn]
    );

    const handlePressOut = useCallback(
        (e: any) => {
            Animated.spring(scaleAnim, {
                toValue: 1,
                useNativeDriver: true,
                stiffness: 300,
                damping: 18,
            }).start();
            onPressOut?.(e);
        },
        [scaleAnim, onPressOut]
    );

    return (
        <Pressable
            onPressIn={handlePressIn}
            onPressOut={handlePressOut}
            style={style}
            {...rest}
        >
            <Animated.View style={{ transform: [{ scale: scaleAnim }] }}>
                {children}
            </Animated.View>
        </Pressable>
    );
}

// ─── NeoShadow ──────────────────────────────────────────────
// Dual-light neumorphism shadow container.

interface NeoShadowProps {
    children: React.ReactNode;
    raised?: boolean;
    depth?: 'sm' | 'md' | 'lg';
    borderRadius?: number;
    style?: StyleProp<ViewStyle>;
}

const SHADOW_CONFIG = {
    sm: { darkOffset: 4, darkRadius: 10, lightOffset: 1, lightRadius: 3, elevation: 3 },
    md: { darkOffset: 6, darkRadius: 14, lightOffset: 2, lightRadius: 4, elevation: 5 },
    lg: { darkOffset: 8, darkRadius: 20, lightOffset: 3, lightRadius: 5, elevation: 8 },
};

export function NeoShadow({
    children,
    raised = true,
    depth = 'md',
    borderRadius = radius.xxl,
    style,
}: NeoShadowProps) {
    const cfg = SHADOW_CONFIG[depth];
    const doff = cfg.darkOffset;
    const loff = cfg.lightOffset;

    const outerShadow: ViewStyle = raised
        ? {
            shadowColor: colors.shadowDark2,
            shadowOffset: { width: doff, height: doff },
            shadowOpacity: 0.42,
            shadowRadius: cfg.darkRadius,
            elevation: cfg.elevation,
            backgroundColor: colors.bg,
            borderRadius,
        }
        : {
            shadowColor: colors.shadowInset,
            shadowOffset: { width: -loff, height: -loff },
            shadowOpacity: 0.5,
            shadowRadius: cfg.lightRadius,
            elevation: 1,
            backgroundColor: colors.bg,
            borderRadius,
        };

    const lightEdge: ViewStyle = raised
        ? { borderRadius, borderTopWidth: 0.5, borderLeftWidth: 0.5, borderColor: 'rgba(255,255,255,0.50)', borderRightWidth: 0, borderBottomWidth: 0 }
        : { borderRadius, borderWidth: 0 };

    return (
        <View style={[outerShadow, style]}>
            <View style={lightEdge}>{children}</View>
        </View>
    );
}

// ─── NeoToggle ──────────────────────────────────────────────

interface NeoToggleProps {
    value: boolean;
    onValueChange: (val: boolean) => void;
    disabled?: boolean;
}

export function NeoToggle({ value, onValueChange, disabled }: NeoToggleProps) {
    const translateX = useRef(new Animated.Value(value ? 26 : 0)).current;

    const toggle = useCallback(() => {
        const next = !value;
        Animated.spring(translateX, {
            toValue: next ? 26 : 0,
            useNativeDriver: true,
            stiffness: 250,
            damping: 20,
        }).start();
        onValueChange(next);
    }, [value, onValueChange, translateX]);

    return (
        <PressableScale
            onPress={toggle}
            scaleIn={0.94}
            disabled={disabled}
            style={{ alignSelf: 'flex-start' }}
        >
            <View
                style={{
                    width: 54,
                    height: 30,
                    borderRadius: 15,
                    backgroundColor: value ? colors.accent : colors.chipBg,
                    justifyContent: 'center',
                    paddingHorizontal: 2,
                    ...(value
                        ? {}
                        : {
                            shadowColor: colors.shadowInset,
                            shadowOffset: { width: -2, height: -2 },
                            shadowOpacity: 0.45,
                            shadowRadius: 3,
                            elevation: 1,
                        }),
                }}
            >
                <Animated.View
                    style={{
                        width: 24,
                        height: 24,
                        borderRadius: 12,
                        backgroundColor: '#ffffff',
                        transform: [{ translateX }],
                        shadowColor: '#000',
                        shadowOffset: { width: 0, height: 1 },
                        shadowOpacity: 0.15,
                        shadowRadius: 2,
                        elevation: 2,
                    }}
                />
            </View>
        </PressableScale>
    );
}

// ─── NeoCard ────────────────────────────────────────────────
// A raised neumorphism card wrapper with enhanced depth.

interface NeoCardProps {
    children: React.ReactNode;
    style?: StyleProp<ViewStyle>;
    depth?: 'sm' | 'md';
    padding?: number;
}

export function NeoCard({ children, style, depth = 'md', padding = spacing.lg }: NeoCardProps) {
    const isMd = depth === 'md';
    return (
        <View style={[{
            marginHorizontal: spacing.lg,
            marginBottom: spacing.lg,
            padding,
            borderRadius: radius.xxl,
            backgroundColor: colors.bg,
            // Enhanced depth shadow
            shadowColor: isMd ? colors.shadowDark2 : colors.shadowDark,
            shadowOffset: { width: isMd ? 7 : 5, height: isMd ? 7 : 5 },
            shadowOpacity: isMd ? 0.42 : 0.36,
            shadowRadius: isMd ? 16 : 12,
            elevation: isMd ? 6 : 4,
            borderTopWidth: 0.5,
            borderLeftWidth: 0.5,
            borderColor: 'rgba(255,255,255,0.50)',
            borderRightWidth: 0,
            borderBottomWidth: 0,
        }, style]}>
            {children}
        </View>
    );
}

// ─── NeoInsetField ──────────────────────────────────────────
// An inset / recessed input field with stronger groove.

interface NeoInsetFieldProps {
    value: string;
    onChangeText: (text: string) => void;
    placeholder?: string;
    placeholderTextColor?: string;
    keyboardType?: 'default' | 'decimal-pad' | 'number-pad';
    multiline?: boolean;
    numberOfLines?: number;
    style?: StyleProp<ViewStyle>;
    inputStyle?: StyleProp<TextStyle>;
    textAlign?: TextStyle['textAlign'];
    editable?: boolean;
}

export function NeoInsetField(props: NeoInsetFieldProps) {
    const { value, onChangeText, placeholder, placeholderTextColor = colors.textMuted, keyboardType = 'default', multiline = false, numberOfLines, style, inputStyle, textAlign, editable = true } = props;
    return (
        <View style={[{
            backgroundColor: colors.inputBg,
            borderRadius: radius.full,
            paddingHorizontal: spacing.xl,
            paddingVertical: multiline ? spacing.md : 0,
            minHeight: multiline ? 60 : 50,
            justifyContent: 'center',
            // Deeper inset shadow
            shadowColor: colors.shadowInset,
            shadowOffset: { width: -3, height: -3 },
            shadowOpacity: 0.55,
            shadowRadius: 6,
            elevation: 1.5,
        }, style]}>
            <TextInput
                value={value}
                onChangeText={onChangeText}
                placeholder={placeholder}
                placeholderTextColor={placeholderTextColor}
                keyboardType={keyboardType}
                multiline={multiline}
                numberOfLines={numberOfLines}
                textAlignVertical={multiline ? 'top' : 'center'}
                style={[{ fontSize: 15, color: colors.textPrimary, paddingVertical: 0, textAlign }, inputStyle]}
                editable={editable}
            />
        </View>
    );
}

// ─── NeuOut ─────────────────────────────────────────────────
// Raised neumorphism container using Skia dual-tone shadows.

const NEUOUT_SHADOWS = {
    sm: { darkDx: 4, darkDy: 4, darkBlur: 8, lightDx: -2, lightDy: -2, lightBlur: 4 },
    md: { darkDx: 8, darkDy: 8, darkBlur: 16, lightDx: -4, lightDy: -4, lightBlur: 8 },
    lg: { darkDx: 12, darkDy: 12, darkBlur: 24, lightDx: -6, lightDy: -6, lightBlur: 12 },
};

interface NeuOutProps {
    children: React.ReactNode;
    style?: StyleProp<ViewStyle>;
    borderRadius?: number;
    depth?: 'sm' | 'md' | 'lg';
}

export function NeuOut({
    children,
    style,
    borderRadius = 36,
    depth = 'md',
}: NeuOutProps) {
    const shadows = NEUOUT_SHADOWS[depth];

    return (
        <View
            style={[
                {
                    backgroundColor: colors.bg,
                    borderRadius,
                    position: 'relative',
                    // RN dark shadow (bottom-right) — no overflow hidden, shadow escapes
                    shadowColor: colors.shadowDark,
                    shadowOffset: { width: shadows.darkDx, height: shadows.darkDy },
                    shadowOpacity: 0.42,
                    shadowRadius: shadows.darkBlur,
                    elevation: depth === 'sm' ? 4 : depth === 'md' ? 8 : 12,
                },
                style,
            ]}
        >
            {children}
            {/* Light edge highlight overlay — absolute, non-interactive, no layout impact */}
            <View
                style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    borderRadius,
                    borderTopWidth: 0.5,
                    borderLeftWidth: 0.5,
                    borderRightWidth: 0,
                    borderBottomWidth: 0,
                    borderColor: 'rgba(255,255,255,0.50)',
                }}
                pointerEvents="none"
            />
        </View>
    );
}

// ─── NeuIn ──────────────────────────────────────────────────
// Inset / recessed neumorphism container using Skia inner shadows.

const NEUIN_SHADOWS = {
    sm: { darkDx: 2, darkDy: 2, darkBlur: 4, lightDx: -1, lightDy: -1, lightBlur: 2 },
    md: { darkDx: 4, darkDy: 4, darkBlur: 8, lightDx: -2, lightDy: -2, lightBlur: 4 },
};

interface NeuInProps {
    children?: React.ReactNode;
    style?: StyleProp<ViewStyle>;
    borderRadius?: number;
    depth?: 'sm' | 'md';
}

export function NeuIn({
    children,
    style,
    borderRadius = 27,
    depth = 'md',
}: NeuInProps) {
    const [layout, setLayout] = useState({ width: 0, height: 0 });
    const shadows = NEUIN_SHADOWS[depth];

    const baseStyle: ViewStyle = {
        backgroundColor: colors.bg,
        borderRadius,
        position: 'relative',
        overflow: 'hidden',
    };

    return (
        <View
            style={[baseStyle, style]}
            onLayout={(e) => {
                const { width, height } = e.nativeEvent.layout;
                if (width > 0 && height > 0) setLayout({ width, height });
            }}
        >
            {/* Skia inner shadows */}
            {layout.width > 0 && (
                <Canvas style={StyleSheet.absoluteFill} pointerEvents="none">
                    <RoundedRect
                        x={0}
                        y={0}
                        width={layout.width}
                        height={layout.height}
                        r={borderRadius}
                        color={colors.bg}
                    >
                        {/* Inner dark shadow (top-left = recessed edge) */}
                        <Shadow
                            dx={shadows.darkDx}
                            dy={shadows.darkDy}
                            blur={shadows.darkBlur}
                            color={colors.shadowInset}
                            inner
                        />
                        {/* Inner light shadow (bottom-right = reflected light) */}
                        <Shadow
                            dx={shadows.lightDx}
                            dy={shadows.lightDy}
                            blur={shadows.lightBlur}
                            color={colors.shadowLight}
                            inner
                        />
                    </RoundedRect>
                </Canvas>
            )}
            <View style={{ position: 'relative', zIndex: 1 }}>{children}</View>
        </View>
    );
}
