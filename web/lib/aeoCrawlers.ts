/**
 * Which AI crawler is which, and what blocking one actually costs.
 *
 * B-095. The crawler table on the AEO screen was six hardcoded verdicts -
 * GPTBot Allowed, ClaudeBot Allowed, PerplexityBot Allowed, Google-Extended
 * Controlled, Applebot-Extended Controlled, CCBot Blocked - rendered without
 * reading a single robots.txt. It said the same six things for a site that had
 * never been scanned.
 *
 * Fabricated would have been bad enough. It was also WRONG about what the bots
 * do, in the direction that costs a client money:
 *
 *     "GPTBot      - Required for ChatGPT citations"
 *     "ClaudeBot   - Required for Claude Search"
 *
 * Neither is true. `GPTBot` and `ClaudeBot` are TRAINING crawlers. The bots that
 * fetch a page to answer a question and cite it are `OAI-SearchBot` and
 * `Claude-SearchBot`, and they are governed by separate robots.txt directives.
 * A client reading that screen would believe that blocking model training costs
 * them ChatGPT and Claude citations. It does not - and the fear is exactly what
 * stops an operator from making a choice they are entitled to make.
 *
 * The classification here mirrors `pipeline/gates/robots_aicrawler_check.py`,
 * which is the authority, and `tests/test_robots_aicrawler_check.py` keeps the
 * three classes disjoint. Same doctrine, same three classes:
 *
 *   CITATION   feeds the index an engine answers from. Blocking = invisible.
 *   TRAINING   collects content to train models. Blocking is a legitimate
 *              business choice and costs no citations.
 *   USER       runs when a person asks the assistant about a page. Five of six
 *              vendors document that these may ignore robots.txt, so neither
 *              verdict is honest and they are listed, never graded.
 */

export type CrawlerClass = "citation" | "training" | "user";
export type CrawlerStatus = null | "allowed" | "blocked";

export type CrawlerSpec = {
  ua: string;
  vendor: string;
  klass: CrawlerClass;
  /** What blocking it actually costs. The old table got this backwards. */
  consequence: string;
};

export const CRAWLERS: CrawlerSpec[] = [
  // Citation - blocking any of these removes the site from that engine's answers.
  { ua: "OAI-SearchBot", vendor: "ChatGPT Search", klass: "citation",
    consequence: "Blocking removes the site from ChatGPT's cited answers." },
  { ua: "Claude-SearchBot", vendor: "Claude Search", klass: "citation",
    consequence: "Blocking removes the site from Claude's cited answers." },
  { ua: "PerplexityBot", vendor: "Perplexity", klass: "citation",
    consequence: "Blocking removes the site from Perplexity's answers." },
  { ua: "Googlebot", vendor: "Google Search & AI Overviews", klass: "citation",
    consequence: "Blocking removes the site from Google, AI Overviews included." },
  { ua: "Bingbot", vendor: "Bing & Copilot", klass: "citation",
    consequence: "Blocking removes the site from Bing and Copilot." },
  { ua: "Applebot", vendor: "Apple Search", klass: "citation",
    consequence: "Blocking removes the site from Siri and Spotlight results." },

  // Training - blocking is a business decision that costs no citations.
  { ua: "GPTBot", vendor: "OpenAI model training", klass: "training",
    consequence: "Blocking opts out of OpenAI model training. Citations are unaffected." },
  { ua: "ClaudeBot", vendor: "Anthropic model training", klass: "training",
    consequence: "Blocking opts out of Anthropic model training. Citations are unaffected." },
  { ua: "Google-Extended", vendor: "Gemini model training", klass: "training",
    consequence: "Blocking opts out of Gemini training. Google Search is unaffected." },
  { ua: "Applebot-Extended", vendor: "Apple model training", klass: "training",
    consequence: "Blocking opts out of Apple model training. Apple Search is unaffected." },
  { ua: "CCBot", vendor: "Common Crawl", klass: "training",
    consequence: "Blocking keeps the site out of the Common Crawl corpus." },

  // User-triggered - listed, never graded.
  { ua: "ChatGPT-User", vendor: "ChatGPT on-demand fetch", klass: "user",
    consequence: "OpenAI states robots.txt may not apply to this bot, so neither verdict would be reliable." },
  { ua: "Claude-User", vendor: "Claude on-demand fetch", klass: "user",
    consequence: "Anthropic states this bot honours robots.txt - the one user-triggered fetcher where a directive is respected." },
];

export const CLASS_LABEL: Record<CrawlerClass, string> = {
  citation: "Citation",
  training: "Training",
  user: "User-triggered",
};

export type AeoRowish = { code?: string; what?: string; detail?: string; severity?: string };

/**
 * Per-crawler status, derived from the scan rows.
 *
 * `aeo.crawler_blocked` and `aeo.training_crawler_blocked` each emit one row per
 * blocked user agent, with the UA in `detail`, or a single pass row when none
 * are blocked. No row for a class at all means that class was never measured -
 * which is `null`, and must not render as "Allowed".
 */
export function crawlerStatuses(
  rows: AeoRowish[] | null | undefined,
): Map<string, CrawlerStatus> {
  const list = Array.isArray(rows) ? rows.filter((r) => r && typeof r === "object") : [];
  const out = new Map<string, CrawlerStatus>();

  const forCode = (code: string) => list.filter((r) => (r.code || "") === code);
  const citation = forCode("aeo.crawler_blocked");
  const training = forCode("aeo.training_crawler_blocked");
  const missing = list.some((r) => (r.code || "") === "aeo.robots_missing");

  for (const spec of CRAWLERS) {
    if (spec.klass === "user") {
      out.set(spec.ua, null); // never graded, by design
      continue;
    }
    const group = spec.klass === "citation" ? citation : training;
    if (missing) {
      // No robots.txt at all. Default-allow is the HTTP reality, but the gate
      // treats a missing robots.txt as a defect rather than a pass, and so does
      // this: we measured, and what we found was "nothing declared".
      out.set(spec.ua, null);
      continue;
    }
    if (group.length === 0) {
      out.set(spec.ua, null);
      continue;
    }
    const named = group.some(
      (r) => (r.detail || "").toLowerCase().includes(spec.ua.toLowerCase()),
    );
    out.set(spec.ua, named ? "blocked" : "allowed");
  }
  return out;
}

export function statusLabel(s: CrawlerStatus): string {
  return s === null ? "Not measured" : s === "allowed" ? "Allowed" : "Blocked";
}

/**
 * The colour. Blocking a TRAINING crawler is not a failure, so it is never red -
 * that was the other half of the old table's message, and it pushed clients
 * toward leaving training scrapers on.
 */
export function statusColor(s: CrawlerStatus, klass: CrawlerClass): string {
  if (s === null) return "#64748b";
  if (klass === "training") return s === "blocked" ? "#0369a1" : "#64748b";
  return s === "allowed" ? "#047857" : "#dc2626";
}

/**
 * A robots.txt block an operator can paste into a client's site.
 *
 * Generated from the classification above rather than hand-written, so it can
 * never drift from it. The previous hand-written version allowed `GPTBot` and
 * `ClaudeBot` - both training crawlers - and named none of the four bots that
 * decide whether the site can be cited at all.
 *
 * The citation half is the recommendation. The training half is presented as a
 * choice, commented out, because blocking model training is the client's call
 * and a snippet that makes it for them is the same overreach as the screen that
 * told them it would cost citations.
 */
export function buildRobotsSnippet(domain: string | null | undefined): string {
  const host = (domain || "").trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
  const citation = CRAWLERS.filter((c) => c.klass === "citation");
  const training = CRAWLERS.filter((c) => c.klass === "training");

  const lines = [
    "# robots.txt for AI Search Visibility",
    "#",
    "# ALLOW these: each one feeds an engine that cites its sources. Blocking any",
    "# of them removes this site from that engine's answers.",
    "",
    ...citation.flatMap((c) => [`User-agent: ${c.ua}`, "Allow: /", ""]),
    "# OPTIONAL: model-training crawlers. Blocking them opts out of training and",
    "# costs no citations. Uncomment only if the client has decided to opt out.",
    "",
    ...training.flatMap((c) => [`# User-agent: ${c.ua}`, "# Disallow: /", ""]),
  ];

  // No domain means no Sitemap line we can honestly write. The old template
  // emitted `https:///sitemap.xml` - a broken URL, in a file that goes live.
  lines.push(
    host
      ? `Sitemap: https://${host}/sitemap.xml`
      : "# Sitemap: https://<domain>/sitemap.xml   <- select a client, or fill this in",
  );
  return lines.join("\n") + "\n";
}
