import { SafeAreaProvider } from "react-native-safe-area-context";

import { AppNavigator } from "./src/AppNavigator";
import { JourneyProvider } from "./src/journey/JourneyContext";

export default function App() {
  return (
    <SafeAreaProvider>
      <JourneyProvider>
        <AppNavigator />
      </JourneyProvider>
    </SafeAreaProvider>
  );
}
