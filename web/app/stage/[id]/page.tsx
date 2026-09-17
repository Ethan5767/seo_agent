import { ReaiApp } from "../../ScannerApp";

/**
 * A pipeline stage by id, e.g. /stage/plan. The sidebar pushes this
 * address when the page opens, so a reload or a shared link lands on it.
 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReaiApp initialNav={{ stage: decodeURIComponent(id) }} />;
}
