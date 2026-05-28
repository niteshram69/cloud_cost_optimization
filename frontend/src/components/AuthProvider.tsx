"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { authStorageKey, loginUser, registerUser } from "@/lib/api";
import type { AuthUser, LoginPayload, RegisterPayload } from "@/lib/types";

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  initialized: boolean;
  login: (payload: LoginPayload) => Promise<AuthUser>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

interface StoredAuth {
  token: string;
  user: AuthUser;
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem(authStorageKey);
    if (!raw) {
      setInitialized(true);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as StoredAuth;
      setToken(parsed.token ?? null);
      setUser(parsed.user ?? null);
    } catch {
      localStorage.removeItem(authStorageKey);
    } finally {
      setInitialized(true);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleUnauthorized = () => {
      setToken(null);
      setUser(null);
      localStorage.removeItem(authStorageKey);
    };

    window.addEventListener("cloudteck:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("cloudteck:unauthorized", handleUnauthorized);
  }, []);

  const persistSession = useCallback((nextToken: string, nextUser: AuthUser) => {
    setToken(nextToken);
    setUser(nextUser);

    if (typeof window !== "undefined") {
      // Note: httpOnly cookie auth is preferred for production web security.
      // LocalStorage is used here for a client-only demo flow.
      localStorage.setItem(
        authStorageKey,
        JSON.stringify({ token: nextToken, user: nextUser } satisfies StoredAuth),
      );
    }
  }, []);

  const login = useCallback(
    async (payload: LoginPayload) => {
      const response = await loginUser(payload);
      persistSession(response.access_token, response.user);
      return response.user;
    },
    [persistSession],
  );

  const register = useCallback(async (payload: RegisterPayload) => {
    await registerUser(payload);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem(authStorageKey);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      token,
      initialized,
      login,
      register,
      logout,
    }),
    [initialized, login, logout, register, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuthContext() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuthContext must be used within AuthProvider");
  return context;
}
