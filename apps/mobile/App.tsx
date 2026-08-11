import { SafeAreaProvider } from "react-native-safe-area-context";

import { AccountPrivacyPanel } from "./src/AccountPrivacyPanel";
import { AppNavigator } from "./src/AppNavigator";
import { AuthProvider } from "./src/auth/AuthContext";
import { I18nProvider } from "./src/i18n/I18nContext";
import { WebLocaleTranslator } from "./src/i18n/WebLocaleTranslator";
import { JourneyProvider } from "./src/journey/JourneyContext";

export default function App() {
  return (
    <SafeAreaProvider>
      <I18nProvider>
        <AuthProvider>
          <WebLocaleTranslator />
          <JourneyProvider>
            <AccountPrivacyPanel />
            <AppNavigator />
          </JourneyProvider>
        </AuthProvider>
      </I18nProvider>
    </SafeAreaProvider>
  );
}
