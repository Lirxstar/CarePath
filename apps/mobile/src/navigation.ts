// React Navigation param lists are intentionally type aliases so they satisfy ParamListBase.
// eslint-disable-next-line @typescript-eslint/consistent-type-definitions
export type RootTabParamList = {
  Tokyo: undefined;
  Today: undefined;
  Coach: undefined;
  "Health Data": undefined;
  "Plan & History": undefined;
};

export const CORE_NAVIGATION_TABS = ["Today", "Coach", "Health Data", "Plan & History"] as const;
export const NAVIGATION_TABS = ["Tokyo", ...CORE_NAVIGATION_TABS] as const;

export type NavigationTab = (typeof NAVIGATION_TABS)[number];
