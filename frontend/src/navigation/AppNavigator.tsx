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

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function InventoryStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#8b5cf6' },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold' },
      }}
    >
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
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#8b5cf6' },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold' },
      }}
    >
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
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#8b5cf6' },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold' },
      }}
    >
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
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#8b5cf6' },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold' },
      }}
    >
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
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: '#8b5cf6',
          tabBarInactiveTintColor: '#9ca3af',
          
          tabBarStyle: {
            backgroundColor: '#fff',
            borderTopColor: '#e5e7eb',
          },
          tabBarLabelStyle: { fontSize: 12, fontWeight: '600' },
        }}
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
