/**
 * Content tools.
 *
 * The one section a competitor has that this product had nothing of. It needs
 * no new data provider: the inputs are the keyword rows the scanner already
 * fetches (`keyword_ideas`, `search_intent`, `keyword_difficulty` all run in
 * `keywords_card`) plus the page findings, and the generator is Claude.
 *
 * Every tool here writes a DRAFT for a human to review. That is not modesty,
 * it is the product's rule: `claim_provenance_check` refuses copy that states
 * a rating, review count, licence number, year-count or warranty term which
 * does not trace to the client's config, a finding's evidence, or the previous
 * version of the file. The shared system prompt below carries that rule into
 * every generation so the gate and the generator agree.
 */

export interface ContentToolField {
  name: string;
  label: string;
  placeholder: string;
  /** A long-form input gets a textarea rather than a single line. */
  multiline?: boolean;
  required?: boolean;
}

export interface ContentTool {
  id: string;
  label: string;
  blurb: string;
  /** What the operator fills in. */
  fields: ContentToolField[];
  /** Turns the filled fields into the user turn. */
  buildPrompt: (values: Record<string, string>, context: ContentContext) => string;
}

export interface ContentContext {
  /** The project's domain, if one is selected. */
  domain?: string;
  /** The project's business name, if known. */
  business?: string;
  /** Keyword rows from the last scan, already measured. */
  keywords?: string[];
}

/**
 * The rule every generation runs under.
 *
 * Written as a constraint on the output, not as a disclaimer bolted on after:
 * a model told "do not invent facts" at the end of a long prompt will still
 * invent them, so this leads.
 */
export const CONTENT_SYSTEM_PROMPT = `You write SEO drafts for a human editor to review before anything is published.

Hard rules, in priority order:

1. Never invent a fact about the business. No ratings, review counts, years in
   business, licence or registration numbers, certifications, awards, warranty
   terms, prices, staff counts, or client names unless they appear verbatim in
   the context you were given. If a claim would strengthen the copy but you do
   not have it, write a bracketed placeholder like [confirm: years in business]
   instead. A draft with placeholders is useful; a draft with invented facts is
   worse than nothing, and the publishing gate will reject it.
2. Use Title Case for every heading. "Roof Repair In Austin", not "Roof repair
   in austin".
3. Do not use em dashes in copy intended for a public page. Use a comma, a full
   stop, or a colon.
4. Do not use possessive contractions in headings. "Summer Is Around The
   Corner", not "Summer's Around The Corner".
5. Write plainly. Short sentences. No filler openers, no "in today's digital
   landscape", no restating the brief back.

Output format: Markdown. Lead with the deliverable, not a preamble. Do not
explain what you are about to do.`;

function contextBlock(ctx: ContentContext): string {
  const lines: string[] = [];
  if (ctx.business) lines.push(`Business name: ${ctx.business}`);
  if (ctx.domain) lines.push(`Domain: ${ctx.domain}`);
  if (ctx.keywords?.length) {
    lines.push(
      `Keywords measured for this site (from the last scan, real search data):`,
      ...ctx.keywords.slice(0, 30).map((k) => `  - ${k}`),
    );
  }
  if (lines.length === 0) {
    return "No project context was supplied. Do not guess at business details; use bracketed placeholders.";
  }
  return `Project context (the only facts you may state about this business):\n${lines.join("\n")}`;
}

export const CONTENT_TOOLS: ContentTool[] = [
  {
    id: "brief",
    label: "SEO Brief Generator",
    blurb:
      "A writer-ready brief for one target keyword: angle, structure, headings, entities to cover, and what to link.",
    fields: [
      { name: "keyword", label: "Target keyword", placeholder: "roof repair austin", required: true },
      { name: "audience", label: "Who is it for", placeholder: "homeowners after storm damage" },
    ],
    buildPrompt: (v, ctx) => `${contextBlock(ctx)}

Write an SEO content brief for the target keyword "${v.keyword}".
${v.audience ? `Intended reader: ${v.audience}.` : ""}

Include, in this order:
- Search intent in one sentence, and what the page must do to satisfy it
- A working title and meta description (title under 60 characters, description under 155)
- An H1, then an H2/H3 outline with a one-line note under each on what it covers
- Entities and subtopics the page should mention to read as authoritative
- Two or three internal links worth adding, described by their topic
- What would make this page better than the pages currently ranking`,
  },
  {
    id: "topics",
    label: "Topic Finder",
    blurb:
      "Turns the keywords this site already ranks for into a clustered content plan, so new pages build on measured demand rather than a guess.",
    fields: [
      { name: "theme", label: "Theme or service", placeholder: "emergency roofing", required: true },
      { name: "count", label: "How many topics", placeholder: "10" },
    ],
    buildPrompt: (v, ctx) => `${contextBlock(ctx)}

Propose ${v.count || "10"} content topics around "${v.theme}".

Group them into clusters (a pillar topic and the supporting pages under it).
For each topic give: the working title, the search intent it serves, the
one-line reason it earns a page of its own, and whether it should be a new page
or a section added to an existing one. Prefer topics connected to the keywords
in the context above, since those are measured demand for this site rather than
a guess. Mark any topic that is not connected to them as speculative.`,
  },
  {
    id: "optimize",
    label: "Content Optimizer",
    blurb:
      "Rewrites an existing page against its target keyword, keeping every factual claim the original made and flagging any it cannot verify.",
    fields: [
      { name: "keyword", label: "Target keyword", placeholder: "metal roofing installation", required: true },
      {
        name: "content",
        label: "Current page copy",
        placeholder: "Paste the page text here",
        multiline: true,
        required: true,
      },
    ],
    buildPrompt: (v, ctx) => `${contextBlock(ctx)}

Improve the page copy below for the target keyword "${v.keyword}".

Rules for this task specifically:
- Keep every factual claim the original makes. Do not add new ones.
- If the original states a fact you cannot trace to it or to the context above,
  leave it exactly as written and list it at the end under "Claims to verify".
- Keep the author's voice. This is an edit, not a rewrite from scratch.

Return: the improved copy first, then a short list of what you changed and why,
then "Claims to verify" if there are any.

--- CURRENT COPY ---
${v.content}`,
  },
  {
    id: "faq",
    label: "FAQ Builder",
    blurb:
      "Question-and-answer blocks shaped for answer engines, with FAQPage JSON-LD. Directly addresses the answer-structure findings the AEO tool reports.",
    fields: [
      { name: "topic", label: "Page or topic", placeholder: "gutter replacement", required: true },
      { name: "count", label: "How many questions", placeholder: "6" },
    ],
    buildPrompt: (v, ctx) => `${contextBlock(ctx)}

Write ${v.count || "6"} frequently asked questions with answers for "${v.topic}".

Shape them for answer engines:
- Each question phrased the way a person would actually type or say it
- Each answer leading with the direct answer in the first sentence, then detail
- Answers between 40 and 80 words
- No invented specifics: use bracketed placeholders for anything about this
  business you were not given

After the questions, output a FAQPage JSON-LD block in a fenced code block,
containing exactly the questions and answers above.`,
  },
  {
    id: "meta",
    label: "Meta Writer",
    blurb:
      "Title tags and meta descriptions for pages the scanner flagged as missing or truncated, written to the length Google actually renders.",
    fields: [
      {
        name: "pages",
        label: "Pages",
        placeholder: "One per line: /services/roofing - Roof repair and replacement",
        multiline: true,
        required: true,
      },
    ],
    buildPrompt: (v, ctx) => `${contextBlock(ctx)}

Write a title tag and meta description for each page listed below.

Constraints:
- Title: under 60 characters, Title Case, the page's primary term near the front
- Description: under 155 characters, active voice, one concrete reason to click
- No invented claims, no superlatives you cannot support
- Do not repeat the business name in every title; use it where it earns space

Return a Markdown table: Page | Title | Characters | Description | Characters

--- PAGES ---
${v.pages}`,
  },
];

export function contentToolById(id: string): ContentTool | undefined {
  return CONTENT_TOOLS.find((t) => t.id === id);
}

/** Fields the operator left blank that the tool needs. */
export function missingRequired(
  tool: ContentTool,
  values: Record<string, string>,
): string[] {
  return tool.fields
    .filter((f) => f.required && !(values[f.name] || "").trim())
    .map((f) => f.label);
}
