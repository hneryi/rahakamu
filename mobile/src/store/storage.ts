/**
 * Persistent storage adapter for zustand.
 *
 * AsyncStorage works on iOS, Android and web (localStorage). We still wrap every
 * call in try/catch because storage can be unavailable (private browsing, a
 * WebView embedded in S-mobiili with storage disabled). In that case the app keeps
 * working with in-memory state instead of crashing.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createJSONStorage, type StateStorage } from 'zustand/middleware';

const memory = new Map<string, string>();

const safeStorage: StateStorage = {
  getItem: async (name) => {
    try {
      return (await AsyncStorage.getItem(name)) ?? memory.get(name) ?? null;
    } catch {
      return memory.get(name) ?? null;
    }
  },
  setItem: async (name, value) => {
    memory.set(name, value);
    try {
      await AsyncStorage.setItem(name, value);
    } catch {
      /* in-memory only */
    }
  },
  removeItem: async (name) => {
    memory.delete(name);
    try {
      await AsyncStorage.removeItem(name);
    } catch {
      /* ignore */
    }
  },
};

export const persistStorage = createJSONStorage(() => safeStorage);
