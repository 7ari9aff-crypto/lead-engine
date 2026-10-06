// Real auth context: Supabase session when configured, legacy cookie session
// (password mode) otherwise. Exposes the same interface the Base44 scaffold
// consumers expect (isLoadingAuth / authError / checkUserAuth / navigateToLogin /
// logout) so pages never know which backend authenticated them.
import React, { createContext, useState, useContext, useEffect, useCallback } from "react";
import * as supabase from "@/lib/supabase";
import { apiGet, apiPost } from "@/lib/leadEngine/api";

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [isLoadingPublicSettings] = useState(false);
  const [authError, setAuthError] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  const checkAuth = useCallback(async () => {
    setAuthError(null);
    try {
      if (supabase.supabaseConfigured) {
        const session = await supabase.currentSession();
        if (session?.user) {
          setUser({
            email: session.user.email,
            name: session.user.email?.split("@")[0] || "user",
            id: session.user.id,
          });
          setIsAuthenticated(true);
          setIsLoadingAuth(false);
          setAuthChecked(true);
          return;
        }
      }
      // Legacy cookie mode (password / open): the backend is the truth.
      const s = await apiGet.session();
      setIsAuthenticated(Boolean(s?.authenticated));
      setUser(s?.authenticated
        ? { email: s?.org_id || "operator", name: "Operator" }
        : null);
    } catch {
      setIsAuthenticated(false);
      setUser(null);
    } finally {
      setIsLoadingAuth(false);
      setAuthChecked(true);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  // Supabase session changes (login elsewhere, expiry) reflect live. When the
  // session drops, do not fight the cookie path — only downgrade if the
  // backend also reports unauthenticated.
  useEffect(() => {
    if (!supabase.supabaseConfigured) return undefined;
    let alive = true;
    supabase.onAuthStateChange((session) => {
      if (!alive) return;
      if (session?.user) {
        setUser({
          email: session.user.email,
          name: session.user.email?.split("@")[0] || "user",
          id: session.user.id,
        });
        setIsAuthenticated(true);
      } else {
        apiGet.session().then((s) => {
          if (!alive) return;
          if (!s?.authenticated) {
            setUser(null);
            setIsAuthenticated(false);
          }
        }).catch(() => {});
      }
    }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const navigateToLogin = useCallback(() => {
    window.location.href = "/login";
  }, []);

  const signInWithPassword = useCallback(async (email, password) => {
    if (supabase.supabaseConfigured) {
      await supabase.signInWithPassword(email, password);
      await checkAuth();
      return;
    }
    await apiPost.login(password); // legacy shared-password mode
    await checkAuth();
  }, [checkAuth]);

  const loginWithPasswordMode = useCallback(async (password) => {
    await apiPost.login(password);
    await checkAuth();
  }, [checkAuth]);

  const logout = useCallback(async () => {
    await supabase.signOut();
    try { await apiPost.logout(); } catch { /* already signed out */ }
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  const value = {
    user,
    isAuthenticated,
    isLoadingAuth,
    isLoadingPublicSettings,
    authError,
    appPublicSettings: null,
    authChecked,
    logout,
    navigateToLogin,
    checkUserAuth: checkAuth,
    checkAppState: checkAuth,
    signInWithPassword,
    loginWithPasswordMode,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
