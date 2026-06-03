import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { recipesApi } from '../api/recipes';
import type { RecipeRecommendation, AIRecommendation } from '../types';
import { neoCard, colors, spacing, radius, shadowMd } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export default function RecipeRecommendationsScreen({ navigation }: Props) {
  const [recommendations, setRecommendations] = useState<RecipeRecommendation[]>([]);
  const [aiRecs, setAiRecs] = useState<AIRecommendation[]>([]);
  const [loadingRules, setLoadingRules] = useState(false);
  const [loadingAi, setLoadingAi] = useState(false);
  const [showAi, setShowAi] = useState(false);

  const fetchRules = async () => {
    setLoadingRules(true);
    try {
      const res = await recipesApi.recommendations({ limit: 20 });
      setRecommendations(res.data);
    } catch {
      Alert.alert('错误', '获取推荐失败');
    } finally {
      setLoadingRules(false);
    }
  };

  const fetchAi = async () => {
    setLoadingAi(true);
    try {
      const res = await recipesApi.aiToday({ limit: 15 });
      setAiRecs(res.data.recommendations);
      setShowAi(true);
    } catch {
      Alert.alert('错误', 'AI 推荐暂不可用');
    } finally {
      setLoadingAi(false);
    }
  };

  const renderRuleItem = (item: RecipeRecommendation) => (
    <TouchableOpacity
      key={item.recipe_id}
      style={styles.item}
      activeOpacity={0.85}
      onPress={() => navigation.navigate('RecipeDetail', { id: item.recipe_id })}
    >
      <View style={styles.itemHeader}>
        <Text style={styles.itemName} numberOfLines={1}>{item.title}</Text>
        <View style={styles.scoreBadge}>
          <Text style={styles.scoreText}>+{item.score}</Text>
        </View>
      </View>
      {item.reason && <Text style={styles.reason}>{item.reason}</Text>}
      {item.matched_inventory_items.length > 0 && (
        <Text style={styles.tagText}>
          {'✅'} 匹配: {item.matched_inventory_items.join(', ')}
        </Text>
      )}
      {item.expiring_inventory_items.length > 0 && (
        <Text style={[styles.tagText, { color: '#f59e0b' }]}>
          {'⚠️'} 临期: {item.expiring_inventory_items.join(', ')}
        </Text>
      )}
      {item.missing_ingredients.length > 0 && (
        <Text style={[styles.tagText, { color: colors.textMuted }]}>
          {'❌'} 缺: {item.missing_ingredients.join(', ')}
        </Text>
      )}
      <View style={styles.itemFooter}>
        {item.is_favorite && <Ionicons name="heart" size={14} color="#ef4444" />}
        {item.is_new_suggestion && (
          <View style={styles.newBadge}>
            <Text style={styles.newBadgeText}>新推荐</Text>
          </View>
        )}
        <Text style={styles.sourceLabel}>{item.source_type === 'user' ? '我的' : item.source_type === 'howtocook' ? 'HowToCook' : 'AI'}</Text>
      </View>
    </TouchableOpacity>
  );

  const renderAiItem = (item: AIRecommendation, idx: number) => (
    <TouchableOpacity
      key={idx}
      style={styles.item}
      activeOpacity={0.85}
      onPress={() => navigation.navigate('RecipeDetail', { id: item.recipe_id })}
    >
      <Text style={styles.itemName}>{item.title}</Text>
      {item.reason && <Text style={styles.reason}>{item.reason}</Text>}
    </TouchableOpacity>
  );

  return (
    <ScrollView style={styles.container}>
      {/* Rule-based */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{'📊'} 规则推荐</Text>
        <Text style={styles.sectionDesc}>根据你的库存匹配的菜谱推荐</Text>
        <TouchableOpacity
          style={[styles.actionBtn, loadingRules && { opacity: 0.6 }]}
          activeOpacity={0.85}
          onPress={fetchRules}
          disabled={loadingRules}
        >
          <Ionicons name="refresh" size={18} color="#ffffff" />
          <Text style={styles.actionBtnText}>
            {loadingRules ? '加载中...' : recommendations.length > 0 ? '刷新推荐' : '获取推荐'}
          </Text>
        </TouchableOpacity>
      </View>

      {loadingRules ? (
        <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
      ) : (
        recommendations.map((item) => renderRuleItem(item))
      )}

      {/* AI Daily */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{'🤖'} AI 今日推荐</Text>
        <Text style={styles.sectionDesc}>AI 根据你的库存和偏好智能推荐</Text>
        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: '#7c3aed' }, loadingAi && { opacity: 0.6 }]}
          activeOpacity={0.85}
          onPress={fetchAi}
          disabled={loadingAi}
        >
          <Ionicons name="sparkles" size={18} color="#ffffff" />
          <Text style={styles.actionBtnText}>
            {loadingAi ? 'AI 思考中...' : showAi ? '重新生成' : '获取 AI 推荐'}
          </Text>
        </TouchableOpacity>
      </View>

      {loadingAi ? (
        <ActivityIndicator size="large" color="#7c3aed" style={styles.loader} />
      ) : showAi && aiRecs.length === 0 ? (
        <Text style={styles.emptyText}>暂无 AI 推荐</Text>
      ) : (
        showAi && aiRecs.map((item, idx) => renderAiItem(item, idx))
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { marginVertical: spacing.xl },
  section: {
    padding: spacing.lg,
    paddingBottom: spacing.sm,
  },
  sectionTitle: { fontSize: 20, fontWeight: '700', color: colors.textPrimary },
  sectionDesc: { fontSize: 14, color: colors.textSecondary, marginTop: spacing.xs },
  actionBtn: {
    backgroundColor: colors.accent,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.35)',
    ...shadowMd,
  },
  actionBtnText: { color: colors.white, fontSize: 15, fontWeight: '600' },
  item: {
    ...neoCard,
    marginHorizontal: spacing.lg - 2,
    marginTop: spacing.md,
    padding: spacing.lg,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemName: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, flex: 1 },
  scoreBadge: {
    backgroundColor: colors.accentBg,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    marginLeft: spacing.sm,
  },
  scoreText: { fontSize: 12, fontWeight: '700', color: colors.accent },
  reason: { fontSize: 14, color: colors.textSecondary, marginTop: spacing.xs, lineHeight: 20 },
  tagText: { fontSize: 13, marginTop: spacing.xs },
  itemFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  newBadge: {
    backgroundColor: '#dbeafe',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.full,
  },
  newBadgeText: { fontSize: 11, fontWeight: '600', color: '#3b82f6' },
  sourceLabel: { fontSize: 12, color: colors.textMuted },
  emptyText: { textAlign: 'center', color: colors.textMuted, fontSize: 15, marginTop: spacing.xl },
});
