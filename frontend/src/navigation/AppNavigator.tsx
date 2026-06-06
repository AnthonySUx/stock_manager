import InventorySummaryScreen from '../screens/InventorySummaryScreen';

import React, { useRef, useEffect } from 'react';
import { View, StyleSheet, TouchableOpacity, Animated } from 'react-native';
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
import { colors } from '../theme';
import { Ionicons } from '@expo/vector-icons';
import { NeuOut, NeuIn } from '../components/NeoComponents';

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
            <Stack.Screen
                name="InventorySummary"
                component={InventorySummaryScreen}
                options={({ route }: any) => ({
                    title: route.params?.title ?? '库存概览',
                })}
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

const TAB_ICONS: Record<string, { focused: keyof typeof Ionicons.glyphMap; unfocused: keyof typeof Ionicons.glyphMap }> = {
    InventoryTab: { focused: 'cube', unfocused: 'cube-outline' },
    RecipeTab: { focused: 'restaurant', unfocused: 'restaurant-outline' },
    SettingsTab: { focused: 'settings', unfocused: 'settings-outline' },
};

const TAB_BAR_WIDTH = 290;
const TAB_COUNT = 3;
const TAB_SLOT = TAB_BAR_WIDTH / TAB_COUNT;
const TAB_HEIGHT = 60;

function AnimatedTabBar({ state, descriptors, navigation }: any) {
    const slideAnim = useRef(new Animated.Value(state.index * TAB_SLOT)).current;

    useEffect(() => {
        Animated.spring(slideAnim, {
            toValue: state.index * TAB_SLOT,
            useNativeDriver: true,
            tension: 120,
            friction: 10,
        }).start();
    }, [state.index]);

    return (
        <NeuOut
            borderRadius={30}
            depth="md"
            style={styles.tabBarOuter}
        >
            <View style={styles.tabBarInner}>
                {/* Sliding indicator */}
                <Animated.View
                    style={[
                        styles.slidingIndicator,
                        {
                            transform: [{ translateX: slideAnim }],
                        },
                    ]}
                >
                    <NeuIn
                        borderRadius={999}
                        depth="sm"
                        style={styles.activeTab}
                    />
                </Animated.View>

                {/* Tab buttons */}
                {state.routes.map((route: any, index: number) => {
                    const { options } = descriptors[route.key];
                    const focused = state.index === index;
                    const config = TAB_ICONS[route.name] || { focused: 'ellipse', unfocused: 'ellipse' };

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
                                size={28}
                                color={focused ? colors.accent : colors.textMuted}
                                style={{ marginTop: 1 }}
                            />
                        </TouchableOpacity>
                    );
                })}
            </View>
        </NeuOut>
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
    tabBarOuter: {
        position: 'absolute',
        bottom: 24,
        alignSelf: 'center',
        width: TAB_BAR_WIDTH,
        height: TAB_HEIGHT,
        overflow: 'hidden',
    },
    tabBarInner: {
        height: TAB_HEIGHT,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 0,
    },
    slidingIndicator: {
        position: 'absolute',
        left: 0,
        top: 4,
        width: TAB_SLOT,
        height: 52,
        justifyContent: 'center',
        alignItems: 'center',
    },
    activeTab: {
        width: TAB_SLOT - 8,
        height: 52,
        justifyContent: 'center',
        alignItems: 'center',
    },
    tabButton: {
        width: TAB_SLOT,
        height: TAB_HEIGHT,
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1,
    },
});
