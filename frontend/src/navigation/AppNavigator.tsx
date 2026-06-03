import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Animated, TouchableOpacity, Dimensions } from 'react-native';
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
import RemindersScreen from '../screens/RemindersScreen';
import SettingsScreen from '../screens/SettingsScreen';
import { colors, shadowSm, shadowInset, radius } from '../theme';
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
        options={{ title: '库存物品' }}
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
        options={{ title: '编辑物品' }}
      />
      <Stack.Screen
        name="ConsumeItem"
        component={ConsumeItemScreen}
        options={{ title: '消耗' }}
      />
    </Stack.Navigator>
  );
}

function RestockStack() {
  return (
    <Stack.Navigator screenOptions={sharedHeaderOptions}>
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
    </Stack.Navigator>
  );
}

function RemindersStack() {
  return (
    <Stack.Navigator screenOptions={sharedHeaderOptions}>
      <Stack.Screen
        name="Reminders"
        component={RemindersScreen}
        options={{ title: '提醒' }}
      />
      <Stack.Screen
        name="ItemDetail"
        component={ItemDetailScreen}
        options={{ title: '物品详情' }}
      />
      <Stack.Screen
        name="EditItem"
        component={EditItemScreen}
        options={{ title: '编辑物品' }}
      />
      <Stack.Screen
        name="ConsumeItem"
        component={ConsumeItemScreen}
        options={{ title: '消耗' }}
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
        options={{ title: '设置' }}
      />
    </Stack.Navigator>
  );
}

const INDICATOR_WIDTH = 64;
const H_PADDING = 8;

function AnimatedTabBar({ state, descriptors, navigation }: any) {
  const [translateX] = useState(() => new Animated.Value(0));
  const tabWidth = (Dimensions.get('window').width - H_PADDING * 2) / state.routes.length;
  const dynamicLeft = H_PADDING + (tabWidth - INDICATOR_WIDTH) / 2;

  useEffect(() => {
    Animated.spring(translateX, {
      toValue: state.index * tabWidth,
      useNativeDriver: true,
      tension: 100,
      friction: 10,
    }).start();
  }, [state.index, tabWidth]);

  return (
    <View style={styles.tabBar}>
      <Animated.View
        style={[
          styles.indicator,
          {
            left: dynamicLeft,
            width: INDICATOR_WIDTH,
            transform: [{ translateX }],
          },
        ]}
      />
      {state.routes.map((route: any, index: number) => {
        const { options } = descriptors[route.key];
        const focused = state.index === index;

        let iconName: keyof typeof Ionicons.glyphMap;
        switch (route.name) {
          case 'InventoryTab':
            iconName = focused ? 'cube' : 'cube-outline';
            break;
          case 'RestockTab':
            iconName = focused ? 'cart' : 'cart-outline';
            break;
          case 'RemindersTab':
            iconName = focused ? 'notifications' : 'notifications-outline';
            break;
          case 'SettingsTab':
            iconName = focused ? 'settings' : 'settings-outline';
            break;
          default:
            iconName = 'ellipse';
        }

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
            activeOpacity={0.7}
          >
            <Ionicons
              name={iconName}
              size={28}
              color={focused ? '#FFFFFF' : colors.textMuted}
            />
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
        tabBar={(props) => <AnimatedTabBar {...props} />}
        screenOptions={{
          headerShown: false,
        }}
      >
        <Tab.Screen
          name="InventoryTab"
          component={InventoryStack}
          options={{}}
        />
        <Tab.Screen
          name="RestockTab"
          component={RestockStack}
          options={{}}
        />
        <Tab.Screen
          name="RemindersTab"
          component={RemindersStack}
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
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    borderWidth: 0.5,
    borderColor: colors.surfaceBorder,
    height: 82,
    paddingBottom: 10,
    paddingTop: 10,
    paddingHorizontal: 8,
    ...shadowSm,
  },
  indicator: {
    position: 'absolute',
    height: 54,
    borderRadius: 27,
    backgroundColor: '#6C3BFF',
    shadowColor: '#6C3BFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 8,
    elevation: 8,
    top: 14,
  },
  tabButton: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
