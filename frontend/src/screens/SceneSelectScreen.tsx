import React from 'react';
import {
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { neoFilterChip, colors, spacing, radius } from '../theme';
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
    navigation.navigate('ItemList', { selectedScene: scene });
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
            style={neoFilterChip(false)}
            activeOpacity={0.7}
            onPress={() => handleSelect(scene)}
          >
            <View style={styles.sceneItem}>
              <Text style={[styles.sceneText, scene === currentScene && styles.sceneTextActive]}>
                {scene}
              </Text>
              {scene === currentScene && (
                <View style={styles.checkmark} />
              )}
            </View>
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
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  sceneItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
  },
  sceneText: {
    flex: 1,
    fontSize: 16,
    color: colors.textPrimary,
  },
  sceneTextActive: {
    color: colors.accent,
    fontWeight: '700',
  },
  checkmark: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.accent,
  },
});
