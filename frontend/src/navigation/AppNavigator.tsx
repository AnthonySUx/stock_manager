import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Animated, TouchableOpacity, Text } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { NavigationContainer } from '@react-navigation/native';

import ItemListScreen from '../screens/ItemListScreen';
import AddItemScreen from '../screens/AddItemScreen';
import ItemDetailScreen from '../screens/ItemDetailScreen';
import EditItemScreen from '../screens/EditItemScreen';
import ConsumeItemScreen from '../screens/ConsumeItemScreen';
import RestockListScreen from '../screens/RestockListScreen';
import AddRestockScreen from '../screens/AddRestockScreen';
import DoneRestockScreen from '../screens/DoneRestockScreen';
import SettingsScreen from '../screens/SettingsScreen';
import RecipeListScreen from '../screens/RecipeListScreen';
import RecipeDetailScreen from '../screens/RecipeDetailScreen';
import RecipeEditScreen from '../screens/RecipeEditScreen';
import RecipeRecommendationsScreen from '../screens/RecipeRecommendationsScreen';
import RecipeCookScreen from '../screens/RecipeCookScreen';
import RecipeExploreScreen from '../screens/RecipeExploreScreen';
import SceneSelectScreen from '../screens/SceneSelectScreen';
import { colors, shadowSm, shadowInset, radius, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

const sharedHeaderOptions = {
  headerStyle: {
    backgroundColor: colors.surface,
    height: 72,
  },
  headerTintColor: colors.textPrimary,
  headerTitleStyle: { fontWeight: '700' as const, fontSize: 24, color: colors.textPrimary },
  headerShadowVisible: false,
  headerTitleAlign: 'center' as const,
};

function InventoryStack() {
  return (
    <Stack.Navigator screenOptions={sharedHeaderOptions}>
      <Stack.Screen
        name="ItemList"
        component={ItemListScreen}
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="AddItem"
        component={AddItemScreen}
        options={{ title: '新增物品' }}
      />
      <Stack.Screen
        name="ItemDetail"
        component={ItemDetailScreen}
        options={{ title: '物品详情' }}
      />
      <Stack.Screen
        name="EditItem"
        component={EditItemScreen}
        options={{ title: '编辑物品', headerBackButtonMenuEnabled: false }}
      />
      <Stack.Screen
        name="ConsumeItem"
        component={ConsumeItemScreen}
        options={{ title: '消耗' }}
      />
      <Stack.Screen
        name="RestockList"
        component={RestockListScreen}
        options={{ title: '补货清单' }}
      />
      <Stack.Screen
        name="AddRestock"
        component={AddRestockScreen}
        options={{ title: '新增补货' }}
      />
      <Stack.Screen
        name="DoneRestock"
        component={DoneRestockScreen}
        options={{ title: '完成补货' }}
      />
      <Stack.Screen
        name="SceneSelect"
        component={SceneSelectScreen}
        options={{ headerShown: false }}
      />

    </Stack.Navigator>
  );
}


function SettingsStack() {
  return (
    <Stack.Navigator screenOptions={sharedHeaderOptions}>
      <Stack.Screen
        name="Settings"
        component={SettingsScreen}
        options={{ headerShown: false }}
      />
    </Stack.Navigator>
  );
}

function RecipeStack() {
  return (
    <Stack.Navigator screenOptions={sharedHeaderOptions}>
      <Stack.Screen
        name="RecipeList"
        component={RecipeListScreen}
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="RecipeDetail"
        component={RecipeDetailScreen}
        options={{ title: '菜谱详情' }}
      />
      <Stack.Screen
        name="RecipeEdit"
        component={RecipeEditScreen}
        options={{ title: '编辑菜谱', headerBackButtonMenuEnabled: false }}
      />
      <Stack.Screen
        name="RecipeRecommendations"
        component={RecipeRecommendationsScreen}
        options={{ title: '推荐菜谱' }}
      />
      <Stack.Screen
        name="RecipeCook"
        component={RecipeCookScreen}
        options={{ title: '烹饪' }}
      />
      <Stack.Screen
        name="RecipeExplore"
        component={RecipeExploreScreen}
        options={{ title: '探索菜谱' }}
      />
    </Stack.Navigator>
  );
}

const TAB_ICONS: Record<string, { focused: keyof typeof Ionicons.glyphMap; unfocused: keyof typeof Ionicons.glyphMap; label: string }> = {
  InventoryTab: { focused: 'cube', unfocused: 'cube-outline', label: '库存' },
  RecipeTab: { focused: 'restaurant', unfocused: 'restaurant-outline', label: '菜谱' },
  SettingsTab: { focused: 'settings', unfocused: 'settings-outline', label: '设置' },
};

const TAB_BAR_WIDTH = 290;
const TAB_COUNT = 3;
const TAB_WIDTH = TAB_BAR_WIDTH / TAB_COUNT;

function AnimatedTabBar({ state, descriptors, navigation }: any) {
  const [translateX] = useState(() => new Animated.Value(0));

  useEffect(() => {
    Animated.spring(translateX, {
      toValue: state.index * TAB_WIDTH,
      useNativeDriver: true,
      tension: 180,
      friction: 16,
    }).start();
  }, [state.index]);

  return (
    <View style={styles.tabBar}>
      <Animated.View
        style={[
          styles.indicator,
          {
            transform: [{ translateX }],
          },
        ]}
      />
      {state.routes.map((route: any, index: number) => {
        const { options } = descriptors[route.key];
        const focused = state.index === index;
        const config = TAB_ICONS[route.name] || { focused: 'ellipse', unfocused: 'ellipse', label: '' };

        const onPress = () => {
          const event = navigation.emit({
            type: 'tabPress',
            target: route.key,
            canPreventDefault: true,
          });
          if (!event.defaultPrevented) {
            navigation.navigate(route.name);
          }
        };

        return (
          <TouchableOpacity
            key={route.key}
            onPress={onPress}
            style={styles.tabButton}
            activeOpacity={1}
          >
            <Ionicons
              name={focused ? config.focused : config.unfocused}
              size={22}
              color={focused ? colors.accent : colors.textMuted}
            />
            <Text
              style={[
                styles.tabLabel,
                { color: focused ? colors.accent : colors.textMuted },
              ]}
            >
              {config.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

export default function AppNavigator() {
  return (
    <NavigationContainer>
      <Tab.Navigator
        initialRouteName="InventoryTab"
        tabBar={(props) => <AnimatedTabBar {...props} />}
        screenOptions={{
          headerShown: false,
        }}
      >
        <Tab.Screen
          name="RecipeTab"
          component={RecipeStack}
          options={{}}
        />
        <Tab.Screen
          name="InventoryTab"
          component={InventoryStack}
          options={{}}
        />
        <Tab.Screen
          name="SettingsTab"
          component={SettingsStack}
          options={{}}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    position: 'absolute',
    bottom: 24,
    alignSelf: 'center',
    width: TAB_BAR_WIDTH,
    flexDirection: 'row',
    backgroundColor: colors.bg,
    borderRadius: 35,
    borderWidth: 0,
    height: 70,
    paddingVertical: 6,
    paddingHorizontal: 6,
    shadowColor: colors.shadowDark,
    shadowOffset: { width: 8, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 18,
    elevation: 10,
  },
  indicator: {
    position: 'absolute',
    width: TAB_WIDTH - 12,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.bg,
    top: 7,
    left: 6,
    shadowColor: colors.shadowInset,
    shadowOffset: { width: -2, height: -2 },
    shadowOpacity: 0.4,
    shadowRadius: 3,
    elevation: 2,
    borderWidth: 0.5,
    borderColor: 'rgba(0,0,0,0.03)',
  },
  tabButton: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1,
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: '600',
    marginTop: 2,
  },
});
