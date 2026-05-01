import { writable } from 'svelte/store';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

function createAuthStore() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  
  const { subscribe, set, update } = writable<AuthState>({
    user: null,
    token,
    isAuthenticated: !!token,
    isLoading: false,
  });

  return {
    subscribe,
    setAuth: (user: User | null, token: string) => {
      localStorage.setItem('token', token);
      update((state) => ({
        ...state,
        user,
        token,
        isAuthenticated: !!user,
      }));
    },
    setUser: (user: User) => {
      update((state) => ({
        ...state,
        user,
        isAuthenticated: true,
      }));
    },
    logout: () => {
      localStorage.removeItem('token');
      set({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
      });
    },
    setLoading: (isLoading: boolean) => {
      update((state) => ({ ...state, isLoading }));
    },
  };
}

export const authStore = createAuthStore();
