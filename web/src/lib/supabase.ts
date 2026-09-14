import { createClient } from "@supabase/supabase-js";

const DEFAULT_SUPABASE_URL = "https://abshiqxxsvdtbdngycpb.supabase.co";
const DEFAULT_SUPABASE_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFic2hpcXh4c3ZkdGJkbmd5Y3BiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODg5NjE2NjIsImV4cCI6MjEwNDUzNzY2Mn0.fiBqBpoO6vMqmbhqoQ2kaH7fqm3CnvjF8Je0EukHsMw";

const url = (
  import.meta.env.VITE_SUPABASE_URL ||
  DEFAULT_SUPABASE_URL
).replace(/\/$/, "");

const publishable =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || DEFAULT_SUPABASE_KEY;

export const supabaseConfigured = Boolean(url && publishable);

export const supabase = createClient(url, publishable, {
  auth: { persistSession: true, autoRefreshToken: true },
});

export async function getAccessToken(): Promise<string | null> {
  if (!supabaseConfigured) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
