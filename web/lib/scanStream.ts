/**
 * Read a `/api/scan` response: an NDJSON event stream on success, or a single
 * JSON `{ error }` object when the route refuses.
 *
 * The hand-rolled reader this replaces dropped every refusal. It never checked
 * `res.ok`, and it parsed only newline-terminated lines, while every refusal the
 * route sends (401, 400, 429 budget, 429 rate limit, unreachable backend) is one
 * JSON object with no trailing newline. The run ended, no error was set, and the
 * operator saw nothing happen.
 *
 * Pure over a `Response`, so it is tested with real `Response` objects and no
 * browser.
 */

export type ScanEvent = Record<string, any>;

export type ScanStreamOutcome = {
  /** Why the scan failed, or null. Never set for a stream that delivered a result. */
  error: string | null;
  /** Paid tools `/api/scan` dropped to stay inside the daily budget. */
  blockedTools: string[];
};

function blockedFrom(res: Response): string[] {
  return (res.headers.get("X-Scan-Blocked-Tools") || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function isNdjson(res: Response): boolean {
  return (res.headers.get("Content-Type") || "").includes("ndjson");
}

async function refusal(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  try {
    const j = JSON.parse(text);
    if (j && typeof j.error === "string" && j.error) return j.error;
  } catch {
    // Not JSON: fall through to the status line.
  }
  const snippet = text.replace(/\s+/g, " ").trim().slice(0, 160);
  return `Scan request failed: HTTP ${res.status}${snippet ? ` (${snippet})` : ""}`;
}

export async function readScanStream(
  res: Response,
  onEvent: (ev: ScanEvent) => void,
  /** What the stream is, for the no-result message ("scan", "apply"). */
  noun = "scan",
): Promise<ScanStreamOutcome> {
  const blockedTools = blockedFrom(res);

  if (!res.ok || !isNdjson(res) || !res.body) {
    return { error: await refusal(res), blockedTools };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let sawResult = false;
  let streamError: string | null = null;
  let malformed = 0;

  const handle = (line: string) => {
    if (!line.trim()) return;
    let ev: ScanEvent;
    try {
      ev = JSON.parse(line);
    } catch {
      malformed++;
      return;
    }
    if (ev && ev.result) sawResult = true;
    if (ev && typeof ev.error === "string" && ev.error && !ev.tool) streamError = ev.error;
    onEvent(ev);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n");
    buf = parts.pop() ?? "";
    for (const part of parts) handle(part);
  }
  buf += decoder.decode();
  handle(buf);

  if (streamError) return { error: streamError, blockedTools };
  if (!sawResult) {
    return {
      error:
        `The ${noun} ended without a result` +
        (malformed ? ` (${malformed} unreadable line${malformed === 1 ? "" : "s"} from the scanner)` : "") +
        ". Check that wf-scan-web is running, then scan again.",
      blockedTools,
    };
  }
  return { error: null, blockedTools };
}
