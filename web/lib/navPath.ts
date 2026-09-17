/**
 * Addresses for sidebar pages that are not tabs: report views, Search Console /
 * GA4 pages, content tools and pipeline stages. Tabs keep their own routes
 * (TAB_ROUTES). Before these existed, opening Keyword Overview left the address
 * bar on the previous tab (/site-audit), so a reload opened the wrong page.
 */

/** The address of a sidebar item that is not a tab (tabs keep TAB_ROUTES). */
export function navPath(item: { view?: string; gsc?: string; content?: string; stage?: string }): string | null {
  if (item.stage) return `/stage/${item.stage}`;
  if (item.content) return `/content/${item.content}`;
  if (item.gsc) return `/gsc/${item.gsc}`;
  if (item.view) return `/view/${item.view}`;
  return null;
}

/** The inverse of navPath: which tool page an address opens. */
export function parseNavPath(pathname: string): { view?: string; gsc?: string; content?: string; stage?: string } {
  const m = pathname.match(/^\/(view|gsc|content|stage)\/([^/]+)\/?$/);
  return m ? { [m[1]]: decodeURIComponent(m[2]) } : {};
}

