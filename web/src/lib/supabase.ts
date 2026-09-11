import { createClient } from "@supabase/supabase-js";

const url = (import.meta.env.VITE_SUPABASE_URL || "").replace(/\/$/, "");
const publishable = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || "";

export const supabaseConfigured = Boolean(url && publishable);

export const supabase = createClient(url || "http://localhost", publishable || "dev", {
  auth: { persistSession: true, autoRefreshToken: true },
});

export async function getAccessToken(): Promise<string | null> {
  if (!supabaseConfigured) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
