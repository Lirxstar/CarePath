import { SafeAreaProvider } from "react-native-safe-area-context";

import { AccountPrivacyPanel } from "./src/AccountPrivacyPanel";
import { AppNavigator } from "./src/AppNavigator";
import { AuthProvider } from "./src/auth/AuthContext";
import { I18nProvider } from "./src/i18n/I18nContext";
import { WebLocaleTranslator } from "./src/i18n/WebLocaleTranslator";
import { JourneyProvider } from "./src/journey/JourneyContext";

function isTokyoEntryPath(): boolean {
  const target = globalThis as unknown as { location?: { pathname?: string } };
  const pathname = target.location?.pathname;
  return pathname === "/tokyo" || pathname === "/tokyo/";
}

export default function App() {
  const tokyoEntry = isTokyoEntryPath();
  return (
    <SafeAreaProvider>
      <I18nProvider>
        <AuthProvider>
          <WebLocaleTranslator />
          <JourneyProvider>
            {tokyoEntry ? null : <AccountPrivacyPanel />}
            <AppNavigator />
          </JourneyProvider>
        </AuthProvider>
      </I18nProvider>
    </SafeAreaProvider>
  );
}
