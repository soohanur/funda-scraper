/**
 * Auth store (zustand). Holds JWT + user info, syncs to localStorage.
 * Hits FastAPI /auth/login and /auth/me.
 */
import { create } from "zustand";
import { api } from "./api";

export type User = {
  id?: string | number;
  email: string;
  name?: string;
};

type AuthState = {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  hydrate: () => Promise<void>;
};

export const useAuth = create<AuthState>((set) => ({
  token: null,
  user: null,
  loading: true,

  async login(email, password) {
    // FastAPI uses OAuth2PasswordRequestForm — form data, username field.
    const form = new URLSearchParams();
    form.append("username", email);
    form.append("password", password);
    const res = await api.post("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    const token: string = res.data.access_token;
    if (typeof window !== "undefined") {
      window.localStorage.setItem("auth_token", token);
    }
    set({ token });
    try {
      const me = await api.get("/auth/me");
      set({ user: { email: me.data.email, name: me.data.full_name, id: me.data.id } });
    } catch {
      set({ user: { email } });
    }
  },

  logout() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("auth_token");
    }
    set({ token: null, user: null });
  },

  async hydrate() {
    if (typeof window === "undefined") {
      set({ loading: false });
      return;
    }
    const token = window.localStorage.getItem("auth_token");
    if (!token) {
      set({ loading: false });
      return;
    }
    set({ token });
    try {
      const me = await api.get("/auth/me");
      set({
        user: { email: me.data.email, name: me.data.full_name, id: me.data.id },
        loading: false,
      });
    } catch {
      // Token bad → clear.
      window.localStorage.removeItem("auth_token");
      set({ token: null, user: null, loading: false });
    }
  },
}));
