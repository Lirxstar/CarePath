import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { useAuth } from "./auth/AuthContext";
import { useJourney } from "./journey/JourneyContext";

function PanelButton({
  label,
  onPress,
  disabled = false,
  secondary = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary ? styles.buttonSecondary : styles.buttonPrimary,
        disabled ? styles.disabled : null,
        pressed && !disabled ? styles.pressed : null,
      ]}
    >
      <Text style={secondary ? styles.buttonSecondaryText : styles.buttonPrimaryText}>{label}</Text>
    </Pressable>
  );
}

export function AccountPrivacyPanel() {
  const {
    runtimeConfig,
    authStatus,
    authBusy,
    authMessage,
    account,
    privateMode,
    privateBusy,
    privateTtlMinutes,
    signInEmail,
    signUpEmail,
    signInGoogle,
    signOut,
    setPrivateMode,
  } = useAuth();
  const { activateSavedData } = useJourney();
  const [expanded, setExpanded] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const authEnabled = runtimeConfig?.auth_enabled === true;
  const busy = authBusy || privateBusy;

  return (
    <View style={styles.panel} testID="account-privacy-panel">
      <View style={styles.summaryRow}>
        <View style={styles.summaryCopy}>
          <Text style={styles.title}>Account & privacy</Text>
          <Text style={styles.summaryText}>
            {authStatus === "authenticated"
              ? `Signed in${account?.email ? ` as ${account.email}` : ""}.`
              : "Account optional · anonymous use remains available."}
            {privateMode ? " Private mode is on." : " Standard storage mode."}
          </Text>
        </View>
        <PanelButton
          secondary
          label={expanded ? "Hide" : "Manage"}
          onPress={() => {
            setExpanded((value) => !value);
          }}
        />
      </View>

      {expanded ? (
        <View style={styles.expanded}>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Optional account</Text>
            <Text style={styles.body}>
              Signing in is never required. An account lets CarePath associate imported data, plans
              and feedback with the same user so they can be continued later.
            </Text>
            {authStatus === "loading" ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator size="small" />
                <Text style={styles.body}>Checking account configuration…</Text>
              </View>
            ) : null}
            {!authEnabled && authStatus !== "loading" ? (
              <Text style={styles.muted}>
                Account sign-in is not configured on this deployment yet. You can continue
                anonymously and use Private mode now.
              </Text>
            ) : null}
            {authEnabled && authStatus !== "authenticated" ? (
              <View style={styles.form}>
                <TextInput
                  accessibilityLabel="Account email"
                  autoCapitalize="none"
                  autoComplete="email"
                  keyboardType="email-address"
                  onChangeText={setEmail}
                  placeholder="Email"
                  style={styles.input}
                  value={email}
                />
                <TextInput
                  accessibilityLabel="Account password"
                  autoCapitalize="none"
                  autoComplete="password"
                  onChangeText={setPassword}
                  placeholder="Password"
                  secureTextEntry
                  style={styles.input}
                  value={password}
                />
                <View style={styles.buttonRow}>
                  <PanelButton
                    label="Sign in"
                    disabled={busy || !email.trim() || password.length < 6}
                    onPress={() => void signInEmail(email, password)}
                  />
                  <PanelButton
                    secondary
                    label="Create account"
                    disabled={busy || !email.trim() || password.length < 6}
                    onPress={() => void signUpEmail(email, password)}
                  />
                  <PanelButton
                    secondary
                    label="Continue with Google"
                    disabled={busy}
                    onPress={signInGoogle}
                  />
                </View>
              </View>
            ) : null}
            {authStatus === "authenticated" ? (
              <View style={styles.form}>
                {account?.profile_exists && account.latest_observation_at && !privateMode ? (
                  <PanelButton
                    label="Use my saved data"
                    disabled={busy}
                    onPress={() => {
                      activateSavedData(
                        account.carepath_user_id,
                        account.latest_observation_at ?? "",
                      );
                      setExpanded(false);
                    }}
                  />
                ) : null}
                {!account?.profile_exists ? (
                  <Text style={styles.muted}>
                    No saved health profile is attached to this account yet. Import your data once
                    to make it available on later sign-ins.
                  </Text>
                ) : null}
                <PanelButton
                  secondary
                  label="Sign out"
                  disabled={busy}
                  onPress={() => void signOut()}
                />
              </View>
            ) : null}
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Private mode</Text>
            <Text style={styles.body}>
              Private mode creates an isolated temporary workspace in server memory. Health records,
              journal content, plans, feedback and coaching interactions are not written to the
              persistent CarePath database. Exiting Private mode destroys the workspace; inactive
              sessions also expire after {String(privateTtlMinutes ?? 60)} minutes.
            </Text>
            <Text style={styles.muted}>
              Turning Private mode on or off starts a clean journey. Load a built-in persona or
              import data after switching modes.
            </Text>
            <PanelButton
              label={privateMode ? "Exit Private mode" : "Turn on Private mode"}
              disabled={busy}
              onPress={() => void setPrivateMode(!privateMode)}
            />
          </View>

          {authMessage ? <Text style={styles.message}>{authMessage}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: "#FFFFFF",
    borderBottomColor: "#DCE5E5",
    borderBottomWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  summaryRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  summaryCopy: { flex: 1 },
  title: { color: "#173B3B", fontSize: 14, fontWeight: "700" },
  summaryText: { color: "#526666", fontSize: 12, lineHeight: 17, marginTop: 2 },
  expanded: { gap: 14, marginTop: 12 },
  section: { gap: 8 },
  sectionTitle: { color: "#173B3B", fontSize: 13, fontWeight: "700" },
  body: { color: "#334F4F", fontSize: 12, lineHeight: 18 },
  muted: { color: "#6A7D7D", fontSize: 11, lineHeight: 16 },
  form: { gap: 8 },
  input: {
    backgroundColor: "#F7F9F9",
    borderColor: "#CBD8D8",
    borderRadius: 8,
    borderWidth: 1,
    color: "#173B3B",
    minHeight: 44,
    paddingHorizontal: 12,
  },
  buttonRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  button: {
    alignItems: "center",
    borderRadius: 8,
    justifyContent: "center",
    minHeight: 40,
    minWidth: 92,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  buttonPrimary: { backgroundColor: "#285C5C" },
  buttonSecondary: {
    backgroundColor: "#E8EFEF",
    borderColor: "#C7D7D7",
    borderWidth: 1,
  },
  buttonPrimaryText: { color: "#FFFFFF", fontSize: 12, fontWeight: "700" },
  buttonSecondaryText: { color: "#285C5C", fontSize: 12, fontWeight: "700" },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.7 },
  loadingRow: { alignItems: "center", flexDirection: "row", gap: 8 },
  message: {
    backgroundColor: "#F1F6F6",
    borderRadius: 8,
    color: "#334F4F",
    fontSize: 11,
    lineHeight: 16,
    padding: 9,
  },
});
