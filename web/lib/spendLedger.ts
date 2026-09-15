/**
 * Server-side spend for the daily scan budget (B-120).
 *
 * The budget summed `scans.cost`, rows only the BROWSER writes after a scan
 * delivers its result. A scan abandoned mid-run (the scanner keeps billing after
 * the socket closes), one that ends in an error after paid tools ran, and
 * concurrent scans admitted against the same stale total were never counted.
 *
 * This ledger lives in the Next server process and needs no schema change:
 *   - `reserve` holds a scan's estimated cost the moment it is admitted, so a
 *     second concurrent scan sees it;
 *   - `settle` replaces the reservation with the cost the stream actually
 *     reported, or keeps the full estimate when the client went away before the
 *     scan finished (the scanner may still be spending);
 *   - `effectiveSpent` = max(saved scans today, settled today) + in-flight, so a
 *     scan counted here and later saved by the browser is not counted twice.
 * A server restart forgets the ledger and falls back to saved scans alone.
 */

type Entry = { user: string; day: string; reserved: number; settled: number | null };

const entries = new Map<string, Entry>();
let seq = 0;

function utcDay(now: number): string {
  return new Date(now).toISOString().slice(0, 10);
}

export function reserve(user: string, estimated: number, now = Date.now()): string {
  const id = `${now}-${++seq}`;
  entries.set(id, { user, day: utcDay(now), reserved: Math.max(0, estimated || 0), settled: null });
  return id;
}

/** `completed`: the stream reached its end. False = the client disconnected. */
export function settle(id: string, reportedCost: number, completed: boolean): void {
  const e = entries.get(id);
  if (!e || e.settled !== null) return;
  const seen = Math.max(0, reportedCost || 0);
  e.settled = completed ? seen : Math.max(seen, e.reserved);
}

export function effectiveSpent(user: string, savedToday: number, now = Date.now()): number {
  const day = utcDay(now);
  let settled = 0;
  let inflight = 0;
  for (const [id, e] of entries) {
    if (e.day !== day) {
      entries.delete(id);
      continue;
    }
    if (e.user !== user) continue;
    if (e.settled === null) inflight += e.reserved;
    else settled += e.settled;
  }
  return Math.max(Math.max(0, savedToday || 0), settled) + inflight;
}

/** Sum the `cost` of finished tools in one NDJSON line, or 0. */
export function costInLine(line: string): number {
  if (!line.includes('"cost"')) return 0;
  try {
    const ev = JSON.parse(line);
    return ev && ev.state === "done" && typeof ev.cost === "number" ? ev.cost : 0;
  } catch {
    return 0;
  }
}

/**
 * Pass a scanner NDJSON stream through unchanged while counting the cost of
 * finished tools; settle the ledger entry when it ends (real cost) or when the
 * client cancels (full estimate kept).
 */
export function meterStream(body: ReadableStream<Uint8Array> | null, ledgerId: string): ReadableStream<Uint8Array> | null {
  if (!body) {
    settle(ledgerId, 0, true);
    return null;
  }
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let reported = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        reported += costInLine(buf + dec.decode());
        settle(ledgerId, reported, true);
        controller.close();
        return;
      }
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n");
      buf = parts.pop() ?? "";
      for (const part of parts) reported += costInLine(part);
      controller.enqueue(value);
    },
    cancel(reason) {
      settle(ledgerId, reported, false);
      return reader.cancel(reason);
    },
  });
}

/** Test seam. */
export function _resetLedger(): void {
  entries.clear();
}
