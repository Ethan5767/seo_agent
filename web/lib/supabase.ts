// Browser Supabase client. Uses the anon key (safe to expose — RLS protects the
// data; only a logged-in user's rows are readable/writable). One shared instance.
import { createClient } from "@supabase/supabase-js";

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);
