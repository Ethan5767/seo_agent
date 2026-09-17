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

/**
 * The project a scan is saved to. The project you have OPEN wins when the
 * scanned site is its site; otherwise the project that owns the domain;
 * otherwise none (the caller creates one). With two projects on one domain,
 * "first in the list" used to win and the open project never got its scan.
 */
export function pickScanProject(
  projects: ProjectLike[] | null | undefined,
  open: ProjectLike | null | undefined,
  scannedUrl: string,
): string | null {
  if (open && sameSite(open.domain || open.website, scannedUrl)) return open.id;
  return ownerOf(projects, scannedUrl);
}

/** Another project in the account already using this domain, or null. */
export function duplicateDomain<T extends ProjectLike>(
  projects: T[] | null | undefined,
  domainOrUrl: string,
  exceptId?: string,
): T | null {
  const d = normDomain(domainOrUrl);
  if (!d) return null;
  return (projects ?? []).find((p) => p.id !== exceptId && projectDomain(p) === d) ?? null;
}
