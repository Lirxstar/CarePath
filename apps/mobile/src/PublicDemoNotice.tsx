import { StyleSheet, Text, View } from "react-native";

import { useAuth } from "./auth/AuthContext";

export const PUBLIC_DEMO_NOTICE = {
  title: "Public research demo",
  body: "You may use built-in synthetic personas or import your own health data. Avoid names, email addresses, medical record numbers, or other directly identifying information. In standard mode, submitted data may be retained on the demo server and are not automatically deleted. CarePath is a research prototype for health-behaviour support and does not provide diagnosis or medical advice.",
  privateBody:
    "Private mode is active. Health records, journal content, plans, feedback and coaching interactions in this workspace are kept in temporary server memory and are not written to the persistent CarePath database. The workspace is destroyed when Private mode is exited and also expires after inactivity. CarePath remains a non-diagnostic research prototype.",
} as const;

export function PublicDemoNotice() {
  const { privateMode } = useAuth();
  if (process.env.EXPO_PUBLIC_CAREPATH_PUBLIC_DEMO !== "true") {
    return null;
  }

  return (
    <View accessibilityRole="summary" style={styles.notice} testID="public-demo-notice">
      <Text style={styles.title}>
        {privateMode ? "Public research demo · Private mode" : PUBLIC_DEMO_NOTICE.title}
      </Text>
      <Text style={styles.body}>
        {privateMode ? PUBLIC_DEMO_NOTICE.privateBody : PUBLIC_DEMO_NOTICE.body}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  notice: {
    backgroundColor: "#FFF7DF",
    borderBottomColor: "#D8BE6A",
    borderBottomWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  title: {
    color: "#493B12",
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 3,
  },
  body: {
    color: "#554A28",
    fontSize: 12,
    lineHeight: 17,
  },
});
