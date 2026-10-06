// Supabase auth client — the dashboard's primary auth surface. Falls back to
// the legacy cookie password mode when the project env is absent (dev).
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const supabaseConfigured = Boolean(url && key);

let client = null;

function getClient() {
  if (!supabaseConfigured) {
    // Warning, not a crash: the API still works through cookie auth, but the
    // operator needs to know the build silently lost Supabase auth.
    console.warn(
      "Supabase auth is disabled for this build. Set VITE_SUPABASE_URL and " +
      "VITE_SUPABASE_PUBLISHABLE_KEY (see web/.env.production).");
    return null;
  }
  if (!client) {
    client = createClient(url, key, {
      auth: { persistSession: true, autoRefreshToken: true },
    });
  }
  return client;
}

export async function getAccessToken() {
  const c = getClient();
  if (!c) return null;
  try {
    const { data } = await c.auth.getSession();
    return data?.session?.access_token || null;
  } catch {
    return null;
  }
}

export async function currentSession() {
  const c = getClient();
  if (!c) return null;
  const { data } = await c.auth.getSession();
  return data?.session || null;
}

// Reports the current session immediately, then on every change. Returns an
// unsubscribe function. Lazy: the SDK only loads when an auth-aware
// component actually mounts.
export async function onAuthStateChange(callback) {
  const c = getClient();
  if (!c) {
    callback(null);
    return () => {};
  }
  const { data } = await c.auth.getSession();
  callback(data?.session || null);
  const listener = c.auth.onAuthStateChange((_event, session) => callback(session));
  return () => listener.data.subscription.unsubscribe();
}

export async function signInWithPassword(email, password) {
  const c = getClient();
  if (!c) throw new Error("Supabase auth is not configured for this build");
  const { data, error } = await c.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

export async function signUp(email, password) {
  const c = getClient();
  if (!c) throw new Error("Supabase auth is not configured for this build");
  const { data, error } = await c.auth.signUp({ email, password });
  if (error) throw error;
  return data;
}

export async function resetPasswordForEmail(email) {
  const c = getClient();
  if (!c) throw new Error("Supabase auth is not configured for this build");
  const { data, error } = await c.auth.resetPasswordForEmail(email);
  if (error) throw error;
  return data;
}

export async function updateUserPassword(password) {
  const c = getClient();
  if (!c) throw new Error("Supabase auth is not configured for this build");
  const { data, error } = await c.auth.updateUser({ password });
  if (error) throw error;
  return data;
}

export async function signOut() {
  const c = getClient();
  if (c) await c.auth.signOut();
}
