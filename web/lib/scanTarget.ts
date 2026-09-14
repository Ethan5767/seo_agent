/**
 * Which project a scan belongs to, and whether it may be merged into the open
 * report.
 *
 * B-126, seen live 2026-09-14: a one-click scan of github.com was filed under the
 * open hospital project, and two later Site Health tests merged into it, so the
 * hospital's On-Page, Content, Schema, Internal links, E-E-A-T and Video pages
 * showed github.com's findings (19 github.com URLs in `seo`, 0 hospital URLs)
 * under the hospital's name. The open project decided where a scan went; the
 * scanned domain did not.
 *
 * Rule: the scanned domain decides. A scan is filed under the project that owns
 * that domain, merged only into a report of that same domain, and a domain no
 * project owns gets a new project rather than borrowing the open one.
 */

export function normDomain(url: string | null | undefined): string {
  return String(url || "")
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/[/?#].*$/, "")
    .replace(/:\d+$/, "")
    .replace(/^www\./i, "")
    .toLowerCase();
}

type ProjectLike = { id: string; domain?: string | null; website?: string | null };

export function projectDomain(p: ProjectLike | null | undefined): string {
  return normDomain(p?.domain || p?.website || "");
}

/** The id of the project that owns the scanned URL's domain, or null. */
export function ownerOf(projects: ProjectLike[] | null | undefined, scannedUrl: string): string | null {
  const d = normDomain(scannedUrl);
  if (!d) return null;
  const hit = (projects ?? []).find((p) => projectDomain(p) === d);
  return hit ? hit.id : null;
}

/** May a scan of `scannedUrl` be merged into a report of `reportUrl`? */
export function sameSite(reportUrl: string | null | undefined, scannedUrl: string): boolean {
  const a = normDomain(reportUrl);
  return Boolean(a) && a === normDomain(scannedUrl);
}
