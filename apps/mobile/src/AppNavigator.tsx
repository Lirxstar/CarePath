import { createBottomTabNavigator, type BottomTabBarProps } from "@react-navigation/bottom-tabs";
import { DefaultTheme, NavigationContainer } from "@react-navigation/native";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useI18n } from "./i18n/I18nContext";
import type { RootTabParamList } from "./navigation";
import { CoachRoute, HealthDataRoute, PlanHistoryRoute, TodayRoute } from "./ResilientRoutes";
import { TokyoScreen } from "./tokyo/TokyoScreen";

const Tab = createBottomTabNavigator<RootTabParamList>();

const CAREPATH_THEME = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    primary: "#285C5C",
    background: "#F4F7F8",
    card: "#FFFFFF",
    text: "#173B3B",
    border: "#DCE5E5",
    notification: "#526666",
  },
};

function browserPathname(): string | null {
  const target = globalThis as unknown as { location?: { pathname?: string } };
  return target.location?.pathname ?? null;
}

function initialRouteName(): keyof RootTabParamList {
  const pathname = browserPathname();
  return pathname === "/tokyo" || pathname === "/tokyo/" ? "Tokyo" : "Today";
}

function syncBrowserPath(routeName: keyof RootTabParamList): void {
  const target = globalThis as unknown as {
    location?: { pathname?: string };
    history?: { pushState: (data: unknown, unused: string, url?: string | null) => void };
  };
  if (target.history === undefined || target.location === undefined) {
    return;
  }
  const nextPath = routeName === "Tokyo" ? "/tokyo" : "/";
  if (target.location.pathname !== nextPath) {
    target.history.pushState({}, "", nextPath);
  }
}

function CarePathTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const { strings } = useI18n();
  const insets = useSafeAreaInsets();
  const activeRoute = state.routes[state.index]?.name as keyof RootTabParamList | undefined;
  const tokyoMode = activeRoute === "Tokyo";
  const tabs: Record<keyof RootTabParamList, { label: string; testId: string }> = {
    Tokyo: { label: "Tokyo", testId: "tab-tokyo" },
    Today: {
      label: tokyoMode ? "Core reviewer" : strings.nav.today,
      testId: tokyoMode ? "tab-core-reviewer" : "tab-today",
    },
    Coach: { label: strings.nav.coach, testId: "tab-coach" },
    "Health Data": { label: strings.nav.healthData, testId: "tab-health-data" },
    "Plan & History": { label: strings.nav.planHistory, testId: "tab-plan-history" },
  };
  const visibleRoutes = tokyoMode
    ? state.routes.filter((route) => route.name === "Tokyo" || route.name === "Today")
    : state.routes;

  return (
    <View
      nativeID="primary-tab-bar"
      style={[styles.tabBar, { paddingBottom: Math.max(insets.bottom, 6) }]}
      testID="primary-tab-bar"
    >
      {visibleRoutes.map((route) => {
        const index = state.routes.findIndex((candidate) => candidate.key === route.key);
        const focused = state.index === index;
        const options = descriptors[route.key]?.options;
        const routeName = route.name as keyof RootTabParamList;
        const metadata = tabs[routeName];
        const onPress = () => {
          const event = navigation.emit({
            type: "tabPress",
            target: route.key,
            canPreventDefault: true,
          });
          if (!focused && !event.defaultPrevented) {
            syncBrowserPath(routeName);
            navigation.navigate(route.name, route.params);
          }
        };
        const onLongPress = () => {
          navigation.emit({ type: "tabLongPress", target: route.key });
        };

        return (
          <Pressable
            key={route.key}
            accessibilityLabel={options?.tabBarAccessibilityLabel ?? metadata.label}
            accessibilityRole="tab"
            accessibilityState={{ selected: focused }}
            nativeID={metadata.testId}
            onLongPress={onLongPress}
            onPress={onPress}
            style={({ pressed }) => [
              styles.tabButton,
              focused ? styles.tabButtonFocused : null,
              pressed ? styles.tabButtonPressed : null,
            ]}
            testID={metadata.testId}
          >
            <Text style={[styles.tabLabel, focused ? styles.tabLabelFocused : null]}>
              {metadata.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function NavigatorBody() {
  const { strings } = useI18n();
  return (
    <NavigationContainer theme={CAREPATH_THEME}>
      <Tab.Navigator
        initialRouteName={initialRouteName()}
        screenOptions={{ headerShown: false }}
        tabBar={(props) => <CarePathTabBar {...props} />}
      >
        <Tab.Screen
          name="Tokyo"
          component={TokyoScreen}
          options={{ tabBarAccessibilityLabel: "CarePath Tokyo" }}
        />
        <Tab.Screen
          name="Today"
          component={TodayRoute}
          options={{ tabBarAccessibilityLabel: strings.nav.today }}
        />
        <Tab.Screen
          name="Coach"
          component={CoachRoute}
          options={{ tabBarAccessibilityLabel: strings.nav.coach }}
        />
        <Tab.Screen
          name="Health Data"
          component={HealthDataRoute}
          options={{ tabBarAccessibilityLabel: strings.nav.healthData }}
        />
        <Tab.Screen
          name="Plan & History"
          component={PlanHistoryRoute}
          options={{ tabBarAccessibilityLabel: strings.nav.planHistory }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

export function AppNavigator() {
  return <NavigatorBody />;
}

const styles = StyleSheet.create({
  tabBar: {
    flexDirection: "row",
    backgroundColor: "#FFFFFF",
    borderTopWidth: 1,
    borderTopColor: "#DCE5E5",
    paddingHorizontal: 4,
    paddingTop: 4,
  },
  tabButton: {
    flex: 1,
    minHeight: 48,
    minWidth: 44,
    paddingHorizontal: 4,
    paddingVertical: 8,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
  },
  tabButtonFocused: { backgroundColor: "#E5EEEE" },
  tabButtonPressed: { opacity: 0.7 },
  tabLabel: {
    color: "#6A7D7D",
    fontSize: 12,
    lineHeight: 16,
    fontWeight: "600",
    textAlign: "center",
  },
  tabLabelFocused: { color: "#285C5C", fontWeight: "700" },
});
