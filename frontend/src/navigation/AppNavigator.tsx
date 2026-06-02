import React from 'react';
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
import { colors, neoRaised, radius } from '../theme';
import { Ionicons } from '@expo/vector-icons';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

const sharedHeaderOptions = {
  headerStyle: {
    backgroundColor: colors.card,
  },
  headerTintColor: colors.textPrimary,
  headerTitleStyle: { fontWeight: 'bold' as const, color: colors.textPrimary },
  headerShadowVisible: false,
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
        options={{ title: '补货列表' }}
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

export default function AppNavigator() {
  return (
    <NavigationContainer>
      <Tab.Navigator
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarActiveTintColor: colors.accent,
          tabBarInactiveTintColor: colors.textMuted,
          tabBarIcon: ({ focused, color, size }) => {
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
            return <Ionicons name={iconName} size={size} color={color} />;
          },
          tabBarStyle: {
            ...neoRaised,
            backgroundColor: colors.card,
            borderTopWidth: 0,
            borderTopLeftRadius: radius.lg,
            borderTopRightRadius: radius.lg,
            borderBottomLeftRadius: 0,
            borderBottomRightRadius: 0,
            elevation: 8,
            shadowOpacity: 0.3,
          },
          tabBarLabelStyle: { fontSize: 12, fontWeight: '600' as const },
        })}
      >
        <Tab.Screen
          name="InventoryTab"
          component={InventoryStack}
          options={{ tabBarLabel: '库存' }}
        />
        <Tab.Screen
          name="RestockTab"
          component={RestockStack}
          options={{ tabBarLabel: '补货' }}
        />
        <Tab.Screen
          name="RemindersTab"
          component={RemindersStack}
          options={{ tabBarLabel: '提醒' }}
        />
        <Tab.Screen
          name="SettingsTab"
          component={SettingsStack}
          options={{ tabBarLabel: '设置' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
