import React from "react";
import { SafeAreaView, StyleSheet } from "react-native";
import { StatusBar } from "expo-status-bar";
import { activateKeepAwakeAsync } from "expo-keep-awake";
import HomeScreen from "./screens/HomeScreen";

// Keep screen awake while relay is active
activateKeepAwakeAsync();

export default function App() {
  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <HomeScreen />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a0a",
  },
});
