/**
 * Lazy Supabase client.
 *
 * `@supabase/supabase-js` is ~120KB of bundle and is only needed once the app
 * actually touches auth (the login page, or an authed API call). Importing it
 * eagerly pulled it into the entry chunk and delayed first paint, so the client
 * is now created on first use via a dynamic import.
 *
 * `supabaseConfigured` stays a cheap synchronous boolean derived from env so
 * callers can branch without awaiting anything.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Single source of truth for the Supabase project: the build-time env.
 *
 * The values are NOT hardcoded here on purpose. They used to be duplicated in
 * this file, `.env.production` and the CI workflow, which made rotation a
 * three-place edit and let the copies drift. Now:
 *
 *   - `web/.env.production`  → the one tracked definition used by `pnpm build`
 *                              (Vite loads it automatically for prod builds)
 *   - `VITE_SUPABASE_URL` / `VITE_SUPABASE_PUBLISHABLE_KEY` → override it
 *                              locally, in CI, or on Vercel
 *
 * The publishable (anon) key is public by design — it ships in the browser
 * bundle — so the risk is drift, not exposure. Rotation procedure lives in
 * `.env.example`.
 */
const url = (import.meta.env.VITE_SUPABASE_URL || "").replace(/\/$/, "");

const publishable = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || "";

export const supabaseConfigured = Boolean(url && publishable);

if (import.meta.env.PROD && !supabaseConfigured) {
  // Warning, not a crash: the API still works through cookie auth, but the
  // operator needs to know the build silently lost Supabase auth.
  // eslint-disable-next-line no-console
  console.warn(
    "[supabase] VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY are missing — " +
      "Supabase auth is disabled for this build. See web/.env.production."
  );
}

let clientPromise: Promise<SupabaseClient> | null = null;

/** Load the Supabase SDK on first use (keeps ~120KB out of the entry chunk). */
export function getSupabase(): Promise<SupabaseClient> {
  if (!clientPromise) {
    clientPromise = import("@supabase/supabase-js").then(({ createClient }) =>
      createClient(url, publishable, {
        auth: { persistSession: true, autoRefreshToken: true },
      })
    );
  }
  return clientPromise;
}

export async function getAccessToken(): Promise<string | null> {
  if (!supabaseConfigured) return null;
  const supabase = await getSupabase();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

type Session = { access_token?: string } | null;

/**
 * Subscribe to auth state, lazily. Reports the current session immediately,
 * then keeps reporting changes. Returns a synchronous unsubscribe function so
 * React effects can clean up without awaiting anything.
 *
 * Before: callers did `supabase.auth.getSession()` + `onAuthStateChange` with a
 * statically imported SDK, which pulled ~120KB into the entry chunk. Now the
 * SDK only loads when an auth-aware component actually mounts.
 */
export async function onAuthChange(
  cb: (session: Session) => void
): Promise<() => void> {
  if (!supabaseConfigured) return () => {};
  const supabase = await getSupabase();
  const { data } = await supabase.auth.getSession();
  cb((data.session as Session) ?? null);
  const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
    cb((session as Session) ?? null);
  });
  return () => listener.subscription.unsubscribe();
}

/** Sign in with email + password. Throws the SDK error on failure. */
export async function signInWithPassword(email: string, password: string): Promise<void> {
  const supabase = await getSupabase();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
}

/** Send a password reset email. */
export async function resetPasswordForEmail(email: string): Promise<void> {
  const supabase = await getSupabase();
  const { error } = await supabase.auth.resetPasswordForEmail(email);
  if (error) throw error;
}

/** Create an account. Returns the raw result so the caller can explain edge cases. */
export async function signUpWithPassword(email: string, password: string, fullName?: string) {
  const supabase = await getSupabase();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: fullName ? { data: { full_name: fullName } } : undefined,
  });
  if (error) throw error;
  return data;
}

/** Sign out. No-op when Supabase isn't configured (local password mode). */
export async function signOut(): Promise<void> {
  if (!supabaseConfigured) return;
  try {
    const supabase = await getSupabase();
    await supabase.auth.signOut();
  } catch {
    /* local mode has no remote session to clear */
  }
}

/** Current access token, if any — used by the auth-aware route guards. */
export async function currentSession(): Promise<Session> {
  if (!supabaseConfigured) return null;
  const supabase = await getSupabase();
  const { data } = await supabase.auth.getSession();
  return (data.session as Session) ?? null;
}

