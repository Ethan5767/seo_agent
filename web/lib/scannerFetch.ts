/**
 * The one way the Next server reaches the Python scanner.
 *
 * B-104. The scanner grew an authorization guard (B-079): every POST it serves
 * spends money, writes to a repository, or starts an AI agent inside one, so it
 * refuses any request without the `X-Scan-Token` it minted. The guard shipped on
 * the Python side and no proxy route was ever given the token, so all five POST
 * proxies — scan, plan, remediate, remediate/dryrun, remediate/apply — were
 * answered 403 for the whole life of the guard. The web UI's entire
 * measure/plan/remediate spine was dead, and it failed silently: the 403 body is
 * one NDJSON-parseable line, so the browser read it as a stream event and the run
 * simply ended. This is B-007 again ("implemented is not wired"), in the
 * direction that hurts most — the wiring was removed from under working code.
 *
 * Routing every call through here is what stops it recurring: there is nowhere
 * else to write `fetch(PYTHON_API + ...)`, and `tests/scannerFetch.test.mjs`
 * asserts no route does.
 */

export const PYTHON_API = process.env.PYTHON_API || "http://127.0.0.1:8765";

/**
 * GET from the scanner.
 *
 * The scanner's `do_GET` carries no token guard — it serves the tool catalogue
 * and the playbooks, which spend nothing and start nothing. It still belongs
 * here: "which calls need the token" is exactly the judgement that was got wrong
 * once, and leaving one hand-written `fetch(PYTHON_API + ...)` in a route is how
 * the next one gets written.
 */
export async function scannerGet(
  path: string,
  { timeoutMs = 10_000 }: { timeoutMs?: number } = {},
): Promise<Response> {
  return fetch(`${PYTHON_API}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
}

/** Why a call could not even be attempted. Never a silent empty result. */
export class ScannerUnconfigured extends Error {}

/**
 * The shared secret. The scanner mints a random token per run unless `SCAN_TOKEN`
 * is set, and a random per-run token is by construction unknowable to this
 * process — so the pair only works when both sides read the same configured
 * value. Missing is refused loudly rather than sent as `""`, because the guard
 * fails closed on an empty token and the operator would see a bare 403 with
 * nothing naming the cause.
 */
export function scannerToken(): string {
  const t = (process.env.SCAN_TOKEN || "").trim();
  if (!t) {
    throw new ScannerUnconfigured(
      "SCAN_TOKEN is not set on the web server, so the scanner will refuse every " +
        "request (403). Set the same SCAN_TOKEN in the repo-root .env (read by " +
        "wf-scan-web) and in web/.env.local, then restart both.",
    );
  }
  return t;
}

/**
 * POST to the scanner with the token attached.
 *
 * `headerTimeoutMs` bounds how long we wait for the response *headers*, and
 * stops there. It used to be an `AbortSignal.timeout` covering the whole fetch,
 * which for a streaming endpoint also bounds the body: a scan streams findings
 * for minutes, so the stream was torn down 10 seconds in, mid-run, and the UI
 * saw a truncated result with no error. Clearing the timer once headers arrive
 * is the difference between "the backend never answered" and "the scan is
 * taking the time a scan takes".
 */
export async function scannerPost(
  path: string,
  body: unknown,
  { headerTimeoutMs = 10_000 }: { headerTimeoutMs?: number } = {},
): Promise<Response> {
  const token = scannerToken();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), headerTimeoutMs);
  try {
    return await fetch(`${PYTHON_API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Scan-Token": token },
      body: typeof body === "string" ? body : JSON.stringify(body),
      // @ts-expect-error - Node fetch streaming duplex flag
      duplex: "half",
      signal: ctrl.signal,
    });
  } finally {
    // Headers are in (or the fetch rejected). The body may still be streaming,
    // and it must not be aborted.
    clearTimeout(timer);
  }
}
