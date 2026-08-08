import { SafeAreaProvider } from "react-native-safe-area-context";

import { AppNavigator } from "./src/AppNavigator";
import { JourneyProvider } from "./src/journey/JourneyContext";
import { PublicDemoNotice } from "./src/PublicDemoNotice";

export default function App() {
  return (
    <SafeAreaProvider>
      <PublicDemoNotice />
      <JourneyProvider>
        <AppNavigator />
      </JourneyProvider>
    </SafeAreaProvider>
  );
}
