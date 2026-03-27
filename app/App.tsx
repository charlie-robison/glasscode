import { StatusBar } from "react-native";
import { activateKeepAwakeAsync } from "expo-keep-awake";
import RelayScreen from "./src/screens/RelayScreen";

activateKeepAwakeAsync();

export default function App() {
  return (
    <>
      <StatusBar barStyle="light-content" />
      <RelayScreen />
    </>
  );
}
