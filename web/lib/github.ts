// List the signed-in user's GitHub repos to pick from at Onboard. Uses the
// GitHub token Supabase captured at login (session.provider_token). Read-only:
// with identity-only scopes this returns PUBLIC repos (private repos + write
// arrive later with a GitHub App for Model B). Best-effort — returns [] on any
// failure (no token yet, expired, rate limit) so the form still works.
import { supabase } from "./supabase";

export async function listRepos(): Promise<string[]> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.provider_token;
  if (!token) return [];
  try {
    const res = await fetch(
      "https://api.github.com/user/repos?per_page=100&sort=updated",
      { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } },
    );
    if (!res.ok) return [];
    const repos = (await res.json()) as Array<{ full_name: string }>;
    return repos.map((r) => r.full_name);
  } catch {
    return [];
  }
}
