import React from 'react';
import {
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { colors, spacing, radius, shadowXs, shadowMd } from '../theme';
import { PressableScale } from '../components/NeoComponents';
import { Ionicons } from '@expo/vector-icons';

type Props = {
    navigation: NativeStackNavigationProp<any>;
};

const ALL_SCENES = ['全部', '冰箱', '冷冻室', '储物柜', '食品储藏室', '柜台', '其他'];

export default function SceneSelectScreen({ navigation, route }: any) {
    const insets = useSafeAreaInsets();
    const currentScene = route?.params?.currentScene || '全部';

    const handleSelect = (scene: string) => {
        route?.params?.onSelectScene?.(scene);
        navigation.goBack();
    };

    return (
        <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
            <View style={styles.header}>
                <PressableScale
                    scaleIn={0.92}
                    onPress={() => navigation.goBack()}
                    style={styles.backBtn}
                >
                    <Ionicons name="arrow-back" size={24} color={colors.textPrimary} />
                </PressableScale>
                <Text style={styles.title}>选择场景</Text>
                <View style={styles.backBtn} />
            </View>
            <Text style={styles.description}>选择要查看的位置</Text>
            <View style={styles.list}>
                {ALL_SCENES.map((scene) => (
                    <TouchableOpacity
                        key={scene}
                        style={[styles.chipBase, scene === currentScene && styles.chipActive]}
                        activeOpacity={0.7}
                        onPress={() => handleSelect(scene)}
                    >
                        <Text style={[styles.sceneText, scene === currentScene && styles.sceneTextActive]}>
                            {scene}
                        </Text>
                    </TouchableOpacity>
                ))}
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.bg,
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.md,
    },
    backBtn: {
        width: 40,
        height: 40,
        justifyContent: 'center',
        alignItems: 'center',
    },
    title: {
        fontSize: 18,
        fontWeight: '700',
        color: colors.textPrimary,
    },
    description: {
        fontSize: 14,
        color: colors.textSecondary,
        textAlign: 'center',
        paddingBottom: spacing.md,
    },
    list: {
        paddingHorizontal: spacing.xl,
        paddingTop: spacing.xl,
        gap: spacing.xxl,
        alignItems: 'center',
    },
    chipBase: {
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.md + 4,
        borderRadius: radius.full,
        backgroundColor: colors.chipBg,
        borderWidth: 0,
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 200,
        alignSelf: 'center',
        ...shadowXs,
    },
    chipActive: {
        backgroundColor: colors.accent,
        ...shadowMd,
    },
    sceneText: {
        fontSize: 17,
        color: colors.textPrimary,
        textAlign: 'center',
    },
    sceneTextActive: {
        color: colors.white,
        fontWeight: '700',
    },
});
