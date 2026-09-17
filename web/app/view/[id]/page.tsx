import { ReaiApp } from "../../ScannerApp";

/**
 * A report view (a tool page) by id, e.g. /view/keyword-overview. The sidebar pushes this
 * address when the page opens, so a reload or a shared link lands on it.
 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReaiApp initialNav={{ view: decodeURIComponent(id) }} />;
}
