import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useRoute, usePreventRemove } from '@react-navigation/native';
import { recipesApi } from '../api/recipes';
import type { RecipeResponse } from '../types';
import { neoCard, neoInput, colors, spacing, radius, shadowMd, shadowXs } from '../theme';
import { PressableScale, NeoInsetField } from '../components/NeoComponents';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

interface IngredientInput {
  ingredient_name: string;
  quantity: string;
  unit: string;
}

interface StepInput {
  step_number: number;
  instruction: string;
}

export default function RecipeEditScreen({ navigation }: Props) {
  const route = useRoute<any>();
  const editId: number | undefined = route.params?.id;
  const isEditing = !!editId;

  const [loading, setLoading] = useState(isEditing);
  const [saving, setSaving] = useState(false);

  const [title, setTitle] = useState(route.params?.title || '');
  const [category, setCategory] = useState('');
  const [description, setDescription] = useState(route.params?.description || '');
  const [difficulty, setDifficulty] = useState('');
  const [servings, setServings] = useState('');
  const [cookTime, setCookTime] = useState('');
  const [ingredients, setIngredients] = useState<IngredientInput[]>([
    { ingredient_name: '', quantity: '', unit: '' },
  ]);
  const [steps, setSteps] = useState<StepInput[]>([
    { step_number: 1, instruction: '' },
  ]);

  const initialValuesRef = useRef<any>(null);
  const isSavingRef = useRef(false);
  const saveHandlerRef = useRef<(() => void) | null>(null);
  const hasUnsavedChangesRef = useRef<() => boolean>(() => false);

  const hasUnsavedChanges = () => {
    if (!initialValuesRef.current) return false;
    const init = initialValuesRef.current;
    return (
      title !== init.title ||
      category !== init.category ||
      description !== init.description ||
      difficulty !== init.difficulty ||
      servings !== init.servings ||
      cookTime !== init.cookTime ||
      JSON.stringify(ingredients) !== JSON.stringify(init.ingredients) ||
      JSON.stringify(steps) !== JSON.stringify(init.steps)
    );
  };
  hasUnsavedChangesRef.current = hasUnsavedChanges;


  useEffect(() => {
    if (editId) {
      fetchRecipe();
    }
  }, [editId]);

  useEffect(() => {
    if (!editId && !initialValuesRef.current) {
      initialValuesRef.current = {
        title,
        category,
        description,
        difficulty,
        servings,
        cookTime,
        ingredients: JSON.parse(JSON.stringify(ingredients)),
        steps: JSON.parse(JSON.stringify(steps)),
      };
    }
  }, []);

  usePreventRemove(hasUnsavedChanges() && !isSavingRef.current, ({ data }) => {
    Alert.alert(
      '有未保存的更改',
      '离开前是否保存更改？',
      [
        { text: '取消', style: 'cancel' },
        { text: '不保存', style: 'destructive', onPress: () => navigation.dispatch(data.action) },
        { text: '保存', onPress: () => {
          isSavingRef.current = true;
          saveHandlerRef.current?.();
        }},
      ]
    );
  });


  const fetchRecipe = async () => {
    try {
      const res = await recipesApi.get(editId!);
      const r = res.data;
      setTitle(r.title);
      setCategory(r.category || '');
      setDescription(r.description || '');
      setDifficulty(r.difficulty || '');
      setServings(r.servings || '');
      setCookTime(r.cook_time_minutes ? String(r.cook_time_minutes) : '');
      setIngredients(
        r.ingredients.length > 0
          ? r.ingredients.map((i) => ({
              ingredient_name: i.ingredient_name,
              quantity: i.quantity || '',
              unit: i.unit || '',
            }))
          : [{ ingredient_name: '', quantity: '', unit: '' }]
      );
      setSteps(
        r.steps.length > 0
          ? r.steps.map((s) => ({ step_number: s.step_number, instruction: s.instruction }))
          : [{ step_number: 1, instruction: '' }]
      );
      initialValuesRef.current = {
        title: r.title,
        category: r.category || '',
        description: r.description || '',
        difficulty: r.difficulty || '',
        servings: r.servings || '',
        cookTime: r.cook_time_minutes ? String(r.cook_time_minutes) : '',
        ingredients: r.ingredients.length > 0
          ? r.ingredients.map((i) => ({
              ingredient_name: i.ingredient_name,
              quantity: i.quantity || '',
              unit: i.unit || '',
            }))
          : [{ ingredient_name: '', quantity: '', unit: '' }],
        steps: r.steps.length > 0
          ? r.steps.map((s) => ({ step_number: s.step_number, instruction: s.instruction }))
          : [{ step_number: 1, instruction: '' }],
      };

    } catch {
      Alert.alert('错误', '未找到菜谱');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  };

  const addIngredient = () => {
    setIngredients([...ingredients, { ingredient_name: '', quantity: '', unit: '' }]);
  };

  const removeIngredient = (idx: number) => {
    if (ingredients.length <= 1) return;
    setIngredients(ingredients.filter((_, i) => i !== idx));
  };

  const updateIngredient = (idx: number, field: keyof IngredientInput, value: string) => {
    const updated = [...ingredients];
    updated[idx] = { ...updated[idx], [field]: value };
    setIngredients(updated);
  };

  const addStep = () => {
    setSteps([...steps, { step_number: steps.length + 1, instruction: '' }]);
  };

  const removeStep = (idx: number) => {
    if (steps.length <= 1) return;
    const updated = steps.filter((_, i) => i !== idx).map((s, i) => ({ ...s, step_number: i + 1 }));
    setSteps(updated);
  };

  const updateStep = (idx: number, value: string) => {
    const updated = [...steps];
    updated[idx] = { ...updated[idx], instruction: value };
    setSteps(updated);
  };

  const handleSave = async () => {
    if (!title.trim()) {
      Alert.alert('错误', '请输入菜谱标题');
      return;
    }
    if (ingredients.some((i) => !i.ingredient_name.trim())) {
      Alert.alert('错误', '请填写所有食材名称');
      return;
    }
    if (steps.some((s) => !s.instruction.trim())) {
      Alert.alert('错误', '请填写所有步骤说明');
      return;
    }

    const payload = {
      title: title.trim(),
      category: category.trim() || null,
      description: description.trim() || null,
      difficulty: difficulty.trim() || null,
      servings: servings.trim() || null,
      cook_time_minutes: cookTime ? parseInt(cookTime, 10) || null : null,
      ingredients: ingredients
        .filter((i) => i.ingredient_name.trim())
        .map((i) => ({
          ingredient_name: i.ingredient_name.trim(),
          quantity: i.quantity.trim() || undefined,
          unit: i.unit.trim() || undefined,
        })),
      steps: steps
        .filter((s) => s.instruction.trim())
        .map((s) => ({
          step_number: s.step_number,
          instruction: s.instruction.trim(),
        })),
    };

    setSaving(true);
    isSavingRef.current = true;

    try {
      if (isEditing) {
        await recipesApi.update(editId!, payload);
        initialValuesRef.current = {
          title,
          category,
          description,
          difficulty,
          servings,
          cookTime,
          ingredients: JSON.parse(JSON.stringify(ingredients)),
          steps: JSON.parse(JSON.stringify(steps)),
        };

        Alert.alert('已更新', '菜谱已更新', [
          { text: '确定', onPress: () => navigation.goBack() },
        ]);
      } else {
        const res = await recipesApi.create(payload as any);
        initialValuesRef.current = {
          title,
          category,
          description,
          difficulty,
          servings,
          cookTime,
          ingredients: JSON.parse(JSON.stringify(ingredients)),
          steps: JSON.parse(JSON.stringify(steps)),
        };

        Alert.alert('已创建', '菜谱已创建', [
          { text: '确定', onPress: () => navigation.goBack() },
        ]);
      }
    } catch (err: any) {
      isSavingRef.current = false;

      Alert.alert('错误', err?.response?.data?.detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    saveHandlerRef.current = handleSave;
  });


  if (loading) {
    return <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />;
  }

  return (
    <ScrollView style={styles.container} keyboardShouldPersistTaps="handled">
      {/* Basic Info */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>基本信息</Text>

        <Text style={styles.label}>标题 *</Text>
        <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="菜谱名称" placeholderTextColor={colors.textMuted} />

        <Text style={styles.label}>分类</Text>
        <TextInput style={styles.input} value={category} onChangeText={setCategory} placeholder="如：中式、西式、甜品" placeholderTextColor={colors.textMuted} />

        <Text style={styles.label}>描述</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          value={description}
          onChangeText={setDescription}
          placeholder="简短描述这道菜..."
          placeholderTextColor={colors.textMuted}
          multiline
          numberOfLines={3}
        />
      </View>

      {/* Details */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>详细信息</Text>

        <Text style={styles.label}>难度</Text>
        <View style={styles.chipRow}>
          {['easy', 'medium', 'hard'].map((v) => (
            <PressableScale
              key={v}
              style={[
                styles.chip,
                difficulty === v && { backgroundColor: colors.accent },
              ]}
              onPress={() => setDifficulty(difficulty === v ? '' : v)}
            >
              <Text style={[styles.chipText, difficulty === v && { color: colors.white }]}>
                {v === 'easy' ? '简单' : v === 'medium' ? '中等' : '困难'}
              </Text>
            </PressableScale>
          ))}
        </View>

        <Text style={styles.label}>份量</Text>
        <TextInput
          style={styles.input}
          value={servings}
          onChangeText={setServings}
          placeholder="如：2-3 人份"
          placeholderTextColor={colors.textMuted}
        />

        <Text style={styles.label}>烹饪时间（分钟）</Text>
        <TextInput
          style={styles.input}
          value={cookTime}
          onChangeText={setCookTime}
          placeholder="如：30"
          placeholderTextColor={colors.textMuted}
          keyboardType="number-pad"
        />
      </View>

      {/* Ingredients */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>食材</Text>
          <PressableScale onPress={addIngredient} style={styles.addBtn}>
            <Ionicons name="add-circle" size={24} color={colors.accent} />
          </PressableScale>
        </View>
        {ingredients.map((ing, idx) => (
          <View key={idx} style={styles.listItemRow}>
            <View style={styles.listItemInputs}>
              <TextInput
                style={[styles.input, styles.inputSmall, { flex: 2 }]}
                value={ing.ingredient_name}
                onChangeText={(v) => updateIngredient(idx, 'ingredient_name', v)}
                placeholder="食材名称"
                placeholderTextColor={colors.textMuted}
              />
              <TextInput
                style={[styles.input, styles.inputSmall, { flex: 1 }]}
                value={ing.quantity}
                onChangeText={(v) => updateIngredient(idx, 'quantity', v)}
                placeholder="数量"
                placeholderTextColor={colors.textMuted}
              />
              <TextInput
                style={[styles.input, styles.inputSmall, { flex: 1 }]}
                value={ing.unit}
                onChangeText={(v) => updateIngredient(idx, 'unit', v)}
                placeholder="单位"
                placeholderTextColor={colors.textMuted}
              />
            </View>
            <PressableScale onPress={() => removeIngredient(idx)} style={styles.removeBtn}>
              <Ionicons name="close-circle" size={22} color={colors.danger} />
            </PressableScale>
          </View>
        ))}
      </View>

      {/* Steps */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>步骤</Text>
          <PressableScale onPress={addStep} style={styles.addBtn}>
            <Ionicons name="add-circle" size={24} color={colors.accent} />
          </PressableScale>
        </View>
        {steps.map((step, idx) => (
          <View key={idx} style={styles.listItemRow}>
            <View style={styles.stepNumber}>
              <Text style={styles.stepNumberText}>{step.step_number}</Text>
            </View>
            <TextInput
              style={[styles.input, { flex: 1, marginLeft: spacing.sm }]}
              value={step.instruction}
              onChangeText={(v) => updateStep(idx, v)}
              placeholder="步骤说明"
              placeholderTextColor={colors.textMuted}
              multiline
            />
            <PressableScale onPress={() => removeStep(idx)} style={styles.removeBtn}>
              <Ionicons name="close-circle" size={22} color={colors.danger} />
            </PressableScale>
          </View>
        ))}
      </View>

      {/* Save */}
      <PressableScale
        style={[styles.saveBtn, saving && { opacity: 0.6 }]}
        scaleIn={0.96}
        onPress={handleSave}
        disabled={saving}
      >
        <Text style={styles.saveBtnText}>{saving ? '保存中...' : isEditing ? '更新菜谱' : '创建菜谱'}</Text>
      </PressableScale>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  loader: { flex: 1, justifyContent: 'center' },
  card: {
    ...neoCard,
    margin: spacing.lg,
    marginBottom: 0,
    padding: spacing.lg,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardTitle: { fontSize: 18, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.md },
  label: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginTop: spacing.md, marginBottom: spacing.xs },
  input: {
    ...neoInput,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    fontSize: 15,
    color: colors.textPrimary,
  },
  multilineInput: {
    minHeight: 70,
    textAlignVertical: 'top',
  },
  inputSmall: { paddingVertical: spacing.sm, fontSize: 14 },
  chipRow: { flexDirection: 'row', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    backgroundColor: colors.chipBg,
    borderWidth: 0.5,
    borderColor: colors.surfaceBorder,
    ...shadowXs,
  },
  chipText: { fontSize: 14, color: colors.textSecondary },
  listItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
    gap: spacing.xs,
  },
  listItemInputs: {
    flex: 1,
    flexDirection: 'row',
    gap: spacing.xs,
  },
  removeBtn: { padding: spacing.xs },
  stepNumber: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.accentBg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepNumberText: { fontSize: 13, fontWeight: '700', color: colors.accent },
  addBtn: { marginBottom: spacing.md },
  saveBtn: {
    backgroundColor: colors.accent,
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    paddingVertical: spacing.lg - 2,
    borderRadius: radius.md,
    alignItems: 'center',
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.24)',
    ...shadowMd,
  },
  saveBtnText: { color: colors.white, fontSize: 16, fontWeight: '700' },
});
