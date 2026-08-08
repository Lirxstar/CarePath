import { StyleSheet, Text, View } from "react-native";

export const PUBLIC_DEMO_NOTICE = {
  title: "Public research demo",
  body: "You may use built-in synthetic personas or import your own health data. Avoid names, email addresses, medical record numbers, or other directly identifying information. Submitted data may be retained on the demo server and are not automatically deleted. CarePath is a research prototype for health-behaviour support and does not provide diagnosis or medical advice.",
} as const;

export function PublicDemoNotice() {
  if (process.env.EXPO_PUBLIC_CAREPATH_PUBLIC_DEMO !== "true") {
    return null;
  }

  return (
    <View accessibilityRole="summary" style={styles.notice} testID="public-demo-notice">
      <Text style={styles.title}>{PUBLIC_DEMO_NOTICE.title}</Text>
      <Text style={styles.body}>{PUBLIC_DEMO_NOTICE.body}</Text>
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
