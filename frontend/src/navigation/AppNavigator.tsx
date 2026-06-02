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
        options={{ title: 'Stock Items' }}
      />
      <Stack.Screen
        name="AddItem"
        component={AddItemScreen}
        options={{ title: 'Add Item' }}
      />
      <Stack.Screen
        name="ItemDetail"
        component={ItemDetailScreen}
        options={{ title: 'Item Details' }}
      />
      <Stack.Screen
        name="EditItem"
        component={EditItemScreen}
        options={{ title: 'Edit Item' }}
      />
      <Stack.Screen
        name="ConsumeItem"
        component={ConsumeItemScreen}
        options={{ title: 'Consume' }}
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
        options={{ title: 'Restock List' }}
      />
      <Stack.Screen
        name="AddRestock"
        component={AddRestockScreen}
        options={{ title: 'Add Restock Item' }}
      />
      <Stack.Screen
        name="DoneRestock"
        component={DoneRestockScreen}
        options={{ title: 'Mark as Done' }}
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
        options={{ title: 'Reminders' }}
      />
      <Stack.Screen
        name="ItemDetail"
        component={ItemDetailScreen}
        options={{ title: 'Item Details' }}
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
        options={{ title: 'Settings' }}
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
          options={{ tabBarLabel: 'Stock' }}
        />
        <Tab.Screen
          name="RestockTab"
          component={RestockStack}
          options={{ tabBarLabel: 'Restock' }}
        />
        <Tab.Screen
          name="RemindersTab"
          component={RemindersStack}
          options={{ tabBarLabel: 'Reminders' }}
        />
        <Tab.Screen
          name="SettingsTab"
          component={SettingsStack}
          options={{ tabBarLabel: 'Settings' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
