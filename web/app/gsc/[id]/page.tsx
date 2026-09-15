import { ReaiApp } from "../../ScannerApp";

/**
 * A Search Console or GA4 page by id, e.g. /gsc/gsc-queries. The sidebar pushes this
 * address when the page opens, so a reload or a shared link lands on it.
 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReaiApp initialNav={{ gsc: decodeURIComponent(id) }} />;
}
