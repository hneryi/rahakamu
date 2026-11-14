/**
 * Root layout: providers + navigation stack.
 *
 * Provider order: gestures → safe areas → React Query → navigation theme.
 * The Stack hosts the tab group plus full-screen routes (chat, onboarding,
 * settings). On desktop web the whole app is rendered inside a phone-sized
 * frame (`AppFrame`) so judges and stakeholders see the mobile UX as intended,
 * and the same build can be dropped into the S-mobiili WebView unchanged.
 */
import '@/global.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { Platform } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { onApiRecovered } from '@/api/client';
import { AppFrame } from '@/components/AppFrame';
import { Toasts } from '@/components/ui/Toasts';
import { useSession } from '@/store/session';
import { useTheme } from '@/theme';

SplashScreen.preventAutoHideAsync().catch(() => {});

export const unstable_settings = { anchor: '(tabs)' };

export default function RootLayout() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
      }),
  );
  const theme = useTheme();
  const hydrated = useSession((s) => s.hydrated);

  useEffect(() => {
    if (hydrated) SplashScreen.hideAsync().catch(() => {});
  }, [hydrated]);

  // The API came back after a spell on demo data: drop everything served from fixtures.
  useEffect(() => onApiRecovered(() => void queryClient.invalidateQueries()), [queryClient]);

  const base = theme.name === 'dark' ? DarkTheme : DefaultTheme;
  const navTheme = { ...base, colors: { ...base.colors, background: theme.c.bgSolid, card: theme.c.bgSolid, primary: theme.c.primary, text: theme.c.text, border: theme.c.border } };

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: theme.c.bgSolid }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider value={navTheme}>
            <AppFrame>
              <StatusBar style={theme.name === 'dark' ? 'light' : 'dark'} />
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: theme.c.bgSolid }, animation: 'default' }}>
                <Stack.Screen name="(tabs)" />
                <Stack.Screen
                  name="chat"
                  options={{
                    presentation: Platform.OS === 'ios' ? 'modal' : 'card',
                    animation: Platform.OS === 'android' ? 'slide_from_bottom' : 'default',
                    gestureEnabled: true,
                  }}
                />
                <Stack.Screen name="onboarding" options={{ animation: 'fade', gestureEnabled: false }} />
                <Stack.Screen name="settings" options={{ animation: Platform.OS === 'android' ? 'slide_from_right' : 'default' }} />
                <Stack.Screen name="characters-lab" />
              </Stack>
              <Toasts />
            </AppFrame>
          </ThemeProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
