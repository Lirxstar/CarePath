import { SafeAreaProvider } from "react-native-safe-area-context";

import { AccountPrivacyPanel } from "./src/AccountPrivacyPanel";
import { AppNavigator } from "./src/AppNavigator";
import { AuthProvider } from "./src/auth/AuthContext";
import { JourneyProvider } from "./src/journey/JourneyContext";
import { PublicDemoNotice } from "./src/PublicDemoNotice";

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <PublicDemoNotice />
        <JourneyProvider>
          <AccountPrivacyPanel />
          <AppNavigator />
        </JourneyProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
