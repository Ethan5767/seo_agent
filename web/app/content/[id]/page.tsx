import { ReaiApp } from "../../ScannerApp";

/**
 * A content tool by id, e.g. /content/brief. The sidebar pushes this
 * address when the page opens, so a reload or a shared link lands on it.
 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReaiApp initialNav={{ content: decodeURIComponent(id) }} />;
}
