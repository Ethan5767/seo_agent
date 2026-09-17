"""Plain-English 'why it matters / how to fix' per finding code, and how bad it is.

Keyed by the finding.code that measure.check_page / providers emit. The copy is
purely advisory for the audit UI — the machine-checkable acceptance still lives
in plan.ACTIONS. Kept as data so it reads and reviews as a table.

`severity` lives here too. It used to be an `_ERROR_CODES` set inside audit.py,
so two modules had to be edited in step to add one code and neither one alone
told you what a code meant. One table now answers all three questions, and a
code that omits `severity` is a warning — the level a finding has by default.
"""
from __future__ import annotations

RECOMMENDATIONS: dict[str, dict] = {
    "health.title_missing": {
        "severity": "error",
        "why": "The <title> is the headline Google shows in results and the strongest on-page ranking signal. A missing title means Google invents one.",
        "fix": "Add a unique <title> of 30-60 characters that names the page's topic and location.",
    },
    "health.title_length": {
        "timeline": "Google usually shows the new headline within days of recrawling the page.",
        "plain": "The headline that appears in Google results is the wrong length, so Google cuts it off or pads it out.",
        "impact": "That headline is the first thing a searcher reads. A cut-off one gets fewer clicks than a complete one.",
        "severity": "error",
        "why": "Titles outside 30-60 characters get truncated or padded by Google, weakening the click.",
        "fix": "Rewrite the <title> to 30-60 characters, front-loading the primary term.",
        "effort": "quick",
        "steps": [
            "The finding's detail carries the current length, e.g. len=14.",
            "Pick the page's primary term. If the site has Search Console, use the query with the most impressions for this URL rather than a guess: that is the phrase people already arrive with.",
            "Write the title as [Primary Term] + [qualifier or location] + [brand], front-loading the term. Google weights the opening words hardest and truncates the tail.",
            "Keep it to 30-60 characters including spaces. Under 30 wastes the slot; over 60 gets cut mid-phrase.",
            "Use Title Case. The heading gate enforces it on client sites.",
            "Make it unique across the site. Two pages sharing a title compete with each other.",
        ],
        "snippet": """<!-- 52 characters -->
<title>Metal Roof Installation In Austin | Acme Roofing</title>

<!-- Next.js App Router -->
export const metadata = {
  title: "Metal Roof Installation In Austin | Acme Roofing",
};""",
        "verify": "The rendered <title> is 30-60 characters and differs from every other page's. Re-run the scan; health.title_length reports passing.",
    },
    "health.desc_missing": {
        "timeline": "Days, once Google recrawls. Google may still write its own summary if it judges yours a poor fit for the search.",
        "plain": "The page has no summary written for search results, so Google picks a sentence from the page itself.",
        "impact": "The sentence it picks is often the wrong one, which costs clicks you already earned by ranking.",
        "severity": "error",
        "why": "With no meta description Google auto-generates the results snippet, often pulling unhelpful text and lowering click-through.",
        "fix": "Add a <meta name=\"description\"> of 120-160 characters that summarises the page and invites the click.",
        "effort": "quick",
        "steps": [
            "Write 120-160 characters saying what the reader gets from this page, not what the company is.",
            "Open with the primary term so it bolds when it matches the query.",
            "End with the action the page supports: get a quote, see pricing, book a visit. The description is ad copy for a free slot.",
            "Describe only what the page really contains. A description promising something the page lacks raises the bounce and Google rewrites it anyway.",
            "Keep it unique per page, like the title.",
        ],
        "snippet": """<!-- 148 characters -->
<meta name="description" content="Metal roof installation in Austin, from tear-off to standing seam. See materials, timelines and what drives the price. Free on-site quote.">

<!-- Next.js App Router -->
export const metadata = {
  description: "Metal roof installation in Austin, from tear-off to ...",
};""",
        "verify": "View source shows the tag at 120-160 characters. Re-run the scan; health.desc_missing reports passing.",
    },
    "health.desc_length": {
        "why": "Descriptions outside 120-160 characters get cut off or look thin in results.",
        "fix": "Rewrite the meta description to 120-160 characters.",
    },
    "health.h1_count": {
        "severity": "error",
        "why": "Exactly one <h1> tells search engines and screen readers the page's single main topic. Zero or many blurs it.",
        "fix": "Keep exactly one <h1> as the page's main heading; demote the rest to <h2>/<h3>.",
    },
    "health.canonical_mismatch": {
        "severity": "error",
        "why": "A missing or wrong canonical lets duplicate URLs compete and splits ranking signals.",
        "fix": "Add <link rel=\"canonical\"> pointing to this page's own preferred URL.",
    },
    "health.noindex_present": {
        "severity": "error",
        "why": "A noindex tag tells Google to drop the page from search entirely — often left in by accident.",
        "fix": "Remove the noindex directive unless the page is genuinely meant to be hidden.",
    },
    "health.og_image_missing": {
        "why": "Without og:image the page shows no preview thumbnail when shared on social or chat, cutting clicks.",
        "fix": "Add <meta property=\"og:image\"> pointing at a representative image.",
    },
    "health.schema_business_missing": {
        "why": "LocalBusiness structured data is how Google and AI engines reliably read the business's name, address and phone. Without it they guess.",
        "fix": "Add LocalBusiness JSON-LD with name, address, phone and URL.",
    },
    "health.schema_breadcrumb_missing": {
        "why": "BreadcrumbList structured data gives search results a clear path and can show breadcrumb rich snippets.",
        "fix": "Add BreadcrumbList JSON-LD reflecting the page's position in the site.",
    },
    "health.img_alt_missing": {
        "why": "Images with no alt attribute are invisible to search image indexing and to screen readers.",
        "fix": "Add a descriptive alt attribute to each content image (empty alt only for decorative images).",
    },
    "health.thin_content": {
        "timeline": "Months, not weeks. This is the slowest item on the list and the one worth starting earliest.",
        "plain": "The page is too short to fully answer what someone is asking when they land on it.",
        "impact": "Visitors go back to Google and click a competitor, and Google notices that pattern over time.",
        "why": "Very short pages rarely satisfy a search intent, so they struggle to rank and are seldom cited by AI answers.",
        "fix": "Expand the copy to genuinely answer the page's question (aim for 500+ words of substance, not padding).",
        "effort": "deep",
        "steps": [
            "Word count is a symptom, not the problem. The problem is an unanswered question, so start by naming the question this page exists to answer.",
            "Read the pages currently ranking for it and list what they cover that this one does not. Cover the gaps, not their structure.",
            "Add the things a buyer actually asks: what it costs and what moves the price, how long it takes, what is included and excluded, what happens if something goes wrong.",
            "Add at least one thing only this business can say: a real project, a real number, a real constraint. That is the information gain that separates the page from a rewrite of the top result.",
            "Put comparable facts in a table. It reads faster and an answer engine can lift it cleanly.",
            "Aim past 500 words, but stop when the question is answered. Padding to hit a count is the failure mode this check is usually a symptom of.",
        ],
        "snippet": "",
        "verify": "The page answers its question without the reader needing another tab, and the scan's Content depth check reports passing.",
    },
    "health.csr_empty_shell": {
        "severity": "warn",
        "why": "The raw HTML contains virtually no readable copy and matches an empty client-side application shell. Crawlers that do not execute JavaScript will see a blank page.",
        "fix": "Serve content server-side (SSR/SSG) so it is present in the initial HTML on first load.",
    },
    "health.csr_content_gap": {
        "severity": "error",
        "why": "AI crawlers (GPTBot, ClaudeBot, PerplexityBot, etc.) do not execute JS, so if the answer/entity content only exists post-render, those crawlers see the same empty shell the raw-HTML scan sees — this finding is a leading indicator, not a false positive to dismiss.",
        "fix": "Serve key answer-first content and JSON-LD structured data in the initial server-rendered HTML (SSR/SSG).",
    },
    "csr_content_gap": {
        "severity": "error",
        "why": "AI crawlers (GPTBot, ClaudeBot, PerplexityBot, etc.) do not execute JS, so if the answer/entity content only exists post-render, those crawlers see the same empty shell the raw-HTML scan sees — this finding is a leading indicator, not a false positive to dismiss.",
        "fix": "Serve key answer-first content and JSON-LD structured data in the initial server-rendered HTML (SSR/SSG).",
    },
    # AEO
    "aeo.robots_missing": {
        "why": "With no robots.txt, AI citation crawlers have no explicit allow and some treat the site as off-limits.",
        "fix": "Ship a robots.txt that Allows the citation crawlers (OAI-SearchBot, ClaudeBot, PerplexityBot, Bingbot, Googlebot) at root.",
    },
    "aeo.crawler_blocked": {
        "timeline": "The block lifts as soon as the file is live. Appearing in AI answers after that can still take weeks.",
        "plain": "A setting on your site is currently telling some AI search tools they are not allowed to read it.",
        "impact": "Those tools cannot mention your business in their answers at all, no matter how good the page is.",
        "why": "If an AI citation crawler is Disallowed, the site cannot be cited in that engine's answers at all.",
        "fix": "Update robots.txt to Allow the blocked citation crawler at root.",
        "effort": "quick",
        "steps": [
            "Open /robots.txt. The finding's detail names which user agent is blocked.",
            "Find the group for that agent, or the User-agent: * group that is catching it.",
            "Add an explicit Allow group for the citation crawlers, as below. An explicit group wins over the wildcard, so this works without loosening anything else.",
            "Do NOT confuse these with the training crawlers (GPTBot, ClaudeBot, Google-Extended, CCBot). Blocking those is a legitimate business choice and does not affect citation; these four are how answers get attributed to you.",
            "Deploy, then fetch https://yourdomain/robots.txt and confirm the group is live at the edge, not just in the repo. A CDN rule can serve a different file than the one you committed.",
        ],
        "snippet": """User-agent: OAI-SearchBot
User-agent: PerplexityBot
User-agent: Googlebot
User-agent: Bingbot
Allow: /

# Training crawlers are a separate decision. Block these only if you do not
# want the content used for model training; it does not affect citation.
# User-agent: GPTBot
# Disallow: /""",
        "verify": "curl -s https://yourdomain/robots.txt shows the Allow group, and the next scan reports AI citation crawlers as passing.",
    },
    "aeo.training_crawler_blocked": {
        "plain": "Your site currently asks AI companies not to use its content for training their models.",
        "impact": "This does not affect whether AI assistants can quote you. It is a choice, and many businesses make it deliberately.",
        "optional": True,
        "timeline": "No action needed. Change it only if you want your content used for model training.",
        # Information, never a defect: blocking training crawlers is a business
        # decision that does not affect whether an engine can cite the site.
        "severity": "info",
        "why": "These crawlers harvest content to train models rather than to cite it. Blocking them does not affect whether AI engines can cite this site, so this is a business decision, not a fault.",
        "fix": "no action needed unless the client wants their content used for model training",
    },
    "aeo.no_answer_structure": {
        "timeline": "Weeks rather than days. The structure has to be recrawled, and being quoted is never guaranteed.",
        "plain": "The page explains things in long paragraphs rather than asking a question and answering it directly underneath.",
        "impact": "AI assistants quote short, direct answers. Yours is written in a shape they tend to skip over.",
        "why": "No question\u2192answer blocks, so AI answer engines can't easily lift a citable answer from the page.",
        "fix": 'add interrogative headings ("How much does X cost?") with a concise answer right below, or FAQ schema',
        "effort": "moderate",
        "steps": [
            "List the questions this page already answers somewhere in its prose. Use the site's own Search Console queries for the page if you have them: those are the questions people actually arrived with.",
            "Turn each into an H2 or H3 phrased as a question, ending in a question mark. An engine matches on the question form.",
            "Put a direct answer in the first two or three sentences under each heading. Answer first, elaborate after. An engine lifts the opening sentences, so a paragraph that warms up for four lines gets skipped.",
            "Keep each answer self-contained. It will be quoted away from the rest of the page, so 'as mentioned above' becomes meaningless.",
            "Lead the page with the single question it most plainly answers.",
            "Once the visible Q&A exists, add FAQPage schema over it (see aeo.answer_schema_missing).",
        ],
        "snippet": """<h2>How Much Does A New Roof Cost In Austin?</h2>
<p>A full replacement runs [confirm: range] for a typical [confirm: size] home.
Asphalt shingle sits at the low end and standing seam metal at the high end.</p>
<p>The three things that move the number most are pitch, decking condition and
tear-off layers. [elaboration continues]</p>""",
        "verify": "Every H2 on the page reads as a question, and the first sentence under each one answers it without needing the rest of the page.",
    },
    "aeo.answer_schema_missing": {
        "timeline": "Usually visible within days of Google recrawling the page. Being quoted by an AI assistant is not guaranteed and can take longer.",
        "plain": "The page does not tell AI assistants what kind of answer it holds, so they have to guess from the writing.",
        "impact": "When ChatGPT or Google's AI answers a question in your industry, it is less likely to quote you and name your business.",
        "why": "FAQPage, QAPage, HowTo and Article tell an answer engine what kind of answer a page holds. Without one it has to guess from prose, and guesses less often become citations.",
        "fix": "add FAQPage, QAPage, HowTo or Article JSON-LD, whichever matches the page",
        "effort": "quick",
        "steps": [
            "Decide what the page actually is. A page answering several questions is a FAQPage. A page walking through a procedure is a HowTo. A single question with one answer is a QAPage. Editorial or news is an Article. Pick one; do not stack them.",
            "Copy the block below into <head>, or into the page component's head slot if the site is a framework app.",
            "Replace every [bracket]. The question and answer text MUST match the visible copy word for word, or Google treats the markup as mismatched and drops the rich result.",
            "If the page has no visible Q&A yet, write that first. Schema describes what is on the page; it cannot add meaning that is not there.",
            "Validate at search.google.com/test/rich-results, then request indexing in Search Console so the change is picked up rather than waiting for the next crawl.",
            "Re-run the scan. aeo.answer_schema_missing should report as passing.",
        ],
        "snippet": """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "[The question, exactly as it appears on the page]",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "[The answer, exactly as it appears on the page]"
      }
    }
  ]
}
</script>""",
        "verify": "Rich Results Test reports the type with no errors, and the question text it extracts matches the visible heading.",
    },
    "aeo.article_author_missing": {
        "why": "Answer engines weigh authorship when deciding what to attribute. An article with no author is harder to cite with confidence.",
        "fix": 'add an "author" to the Article JSON-LD, with a Person or Organization name',
    },
    # Video. These codes come from rows.make_row("video"), so they are stamped
    # from the row's own label: "Video snippets" -> video.video_snippets.
    "video.video_snippets": {
        "timeline": "Days to a few weeks, once Google recrawls the page and validates the markup.",
        "plain": "You have a video on the page, but nothing on the page tells Google it is a video or what it shows.",
        "impact": "You lose a place in Google's video results, which is a second way for people to find this page.",
        "severity": "warn",
        "why": "A video with no VideoObject markup is invisible as a video. Google cannot show it in the video carousel or as a key-moments result, and an answer engine cannot tell there is a demonstration on the page at all.",
        "fix": "add VideoObject JSON-LD describing each embedded video",
        "effort": "quick",
        "steps": [
            "List every video embedded on the page: YouTube iframes, Vimeo embeds, and native <video> tags all count.",
            "Add one VideoObject per video. Do not describe a video that is not on the page.",
            "name and description must match what the video actually shows, and description should carry the target phrase naturally rather than stuffed. This is the keyword match that matters: it is what an engine reads to decide which query the video answers.",
            "uploadDate must be the real publish date in ISO 8601. An invented date is the kind of claim the provenance gate refuses.",
            "thumbnailUrl must be a real, reachable image. Google drops the result if it 404s.",
            "duration is ISO 8601 duration: PT5M30S is five minutes thirty.",
            "Add a transcript on the page if there is not one. It is the single biggest lever here: it turns a video into text an engine can quote, and it is what makes the video citable rather than merely indexed.",
            "Validate at search.google.com/test/rich-results and re-run the scan.",
        ],
        "snippet": """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "[Video title, matching what the video shows]",
  "description": "[One or two sentences that name the topic and the target phrase]",
  "thumbnailUrl": ["https://[domain]/[thumbnail].jpg"],
  "uploadDate": "[YYYY-MM-DD]",
  "duration": "PT[M]M[S]S",
  "contentUrl": "https://[domain]/[video].mp4",
  "embedUrl": "https://www.youtube.com/embed/[id]",
  "transcript": "[Full transcript text, if the page carries one]"
}
</script>""",
        "verify": "Rich Results Test reports VideoObject with no errors, the thumbnail URL resolves, and the scan's Video check reports passing.",
    },
    "video.video_metadata": {
        "timeline": "YouTube picks up a description within hours. Search results move over the following weeks.",
        "plain": "Some of your videos have no description written on YouTube.",
        "impact": "Neither YouTube search nor Google can tell what those videos cover, so they surface far less often than they could.",
        "severity": "warn",
        "why": "A video with no description on YouTube gives both YouTube search and the embedding page nothing to read. The embed inherits that emptiness.",
        "fix": "write a real description on YouTube for each video the page embeds",
        "effort": "moderate",
        "steps": [
            "The finding's detail names which videos are thin. Open each on YouTube.",
            "Write a description that opens with the question the video answers, in the words someone would search. The first line is what shows in search and in the embed preview.",
            "Add timestamps as chapters. They become key-moments in Google results, which is a second entry point into the same video.",
            "Link back to the page that embeds it, so the video and the page reinforce each other.",
            "Re-run the scan with the Video tool enabled; the metadata row reads live from the YouTube Data API, so it will reflect the change on the next run.",
        ],
        "snippet": """[Question the video answers, in plain search language]

[Two or three sentences on what the viewer will learn.]

Chapters:
0:00 [Section]
1:24 [Section]
3:40 [Section]

Full write-up: https://[domain]/[the page that embeds this]""",
        "verify": "The next scan's Video metadata row reports every video carrying full metadata rather than naming thin ones.",
    },
    # Performance (CrUX)
    "crux.lcp_above_good": {
        "why": "Largest Contentful Paint over 2.5s is the moment users decide a page is slow; Google penalises it and AI engines cite it less.",
        "fix": "Optimise the largest element: compress/serve the hero image well, remove render-blocking resources, and speed up the server response.",
    },
    "crux.inp_above_good": {
        "why": "Interaction to Next Paint over 200ms makes taps and clicks feel frozen, driving users away.",
        "fix": "Break up long JavaScript tasks, defer non-critical scripts, and reduce main-thread work.",
    },
    "crux.cls_above_good": {
        "why": "Cumulative Layout Shift over 0.1 means the page jumps while loading, causing misclicks and frustration.",
        "fix": "Set width/height on images and embeds, and reserve space for anything that loads late.",
    },
    "crux.disabled": {
        "why": "Real field performance (LCP/INP/CLS) comes from Google's CrUX dataset and needs an API key.",
        "fix": "Set CRUX_API_KEY (free from Google) to enable Core Web Vitals in the audit.",
    },
}

_GENERIC = {
    "why": "This issue affects how search engines or AI answer engines read the page.",
    "fix": "Review the finding detail and correct the underlying markup or content.",
}


def recommend(code: str, detail: str = "") -> dict:
    """Return {'why','fix'} for a finding code, or a safe generic fallback."""
    return RECOMMENDATIONS.get(code, _GENERIC)


#: Effort bands, so a worklist can be ordered by what it costs to do.
#: quick    — one file, minutes, no judgement call
#: moderate — one file, but needs a decision or real copy
#: deep     — research, writing, or work across several pages
EFFORTS = ("quick", "moderate", "deep")

_EMPTY_PLAYBOOK = {
    "effort": "moderate",
    "steps": [],
    "snippet": "",
    "verify": "",
    "timeline": "",
    "optional": False,
}

#: `timeline` answers "when will we see this work?" before the client asks it in
#: week three. Google's own guidance is the honest form and the source of this
#: field: "Some changes might take effect in a few hours, others could take
#: several months", and "you likely want to wait a few weeks to assess whether
#: your work had beneficial effects". A finding with no timeline gets the
#: cautious default rather than an implied promise. We state a range, never a
#: date, and never a predicted position: nobody can guarantee a ranking.
#:
#: `optional` marks a finding that is a legitimate business CHOICE rather than a
#: defect - blocking AI training crawlers is the clearest case. Every serious
#: tool ships this permission explicitly (Google Search Console: "there is
#: nothing you need to do"; other tools: "feel free to ignore this recommendation")
#: because a severity system with no documented bottom reads as an infinite
#: to-do list. Ours had no way to say it, so it was carried in a code comment.

#: Two registers, because two people read this.
#:
#: `plain` and `impact` are for the CLIENT, who does not write code and should
#: never be shown `aeo.answer_schema_missing` or a block of JSON-LD. One
#: sentence on what is wrong, one on what it costs them, both in business words.
#:
#: `steps`, `snippet` and `verify` are for whoever implements - the operator, or
#: the remediation agent. That half is deliberately technical.
#:
#: A finding with no `plain` falls back to `why`, which is written for an
#: operator and will read as jargon. That fallback is a gap to fill, not a
#: design: `plain_coverage()` reports how many are still missing.


def playbook(code: str) -> dict:
    """How to actually fix this finding: ordered steps, the markup to paste, and
    the check that proves it worked.

    `fix` is one line, which is a hint and not a procedure: "add FAQPage, QAPage,
    HowTo or Article JSON-LD, whichever matches the page" still leaves someone
    to work out which type applies, which fields are required, where the block
    goes and how to tell it landed. An audit that only names the defect makes
    the reader do the work; the product is meant to do it.

    Returns the same shape for every code. A code with no playbook yet returns
    empty lists and strings rather than None, so a caller renders "no steps
    recorded" instead of crashing - and so an unwritten playbook is visibly
    unwritten rather than silently absent.
    """
    entry = RECOMMENDATIONS.get(code) or {}
    return {
        "code": code,
        "effort": entry.get("effort", _EMPTY_PLAYBOOK["effort"]),
        # Client register.
        "plain": entry.get("plain", ""),
        "impact": entry.get("impact", ""),
        # Implementer register.
        "steps": list(entry.get("steps") or []),
        "snippet": entry.get("snippet", ""),
        "verify": entry.get("verify", ""),
        "timeline": entry.get("timeline", ""),
        "optional": bool(entry.get("optional", False)),
        "why": entry.get("why", _GENERIC["why"]),
        "fix": entry.get("fix", _GENERIC["fix"]),
        "severity": severity_of(code),
    }


def plain_coverage() -> dict:
    """How much of the table can be shown to a client without jargon.

    Reported rather than assumed: a missing `plain` silently falls back to `why`,
    which is operator language, so the gap has to be countable or it will not be
    closed.
    """
    total = len(RECOMMENDATIONS)
    plain = sum(1 for e in RECOMMENDATIONS.values() if e.get("plain"))
    steps = sum(1 for e in RECOMMENDATIONS.values() if e.get("steps"))
    return {"codes": total, "plain": plain, "steps": steps,
            "missing_plain": sorted(c for c, e in RECOMMENDATIONS.items() if not e.get("plain"))}


def has_playbook(code: str) -> bool:
    """True when someone has written the steps out. Used by the UI to show a
    "How to fix" action only where there is something behind it."""
    return bool((RECOMMENDATIONS.get(code) or {}).get("steps"))


def severity_of(code: str) -> str:
    """How bad a finding of this code is. Unknown codes, and codes that do not
    declare one, are warnings: bad enough to show, never bad enough to claim an
    urgency the table never stated."""
    return RECOMMENDATIONS.get(code, {}).get("severity", "warn")
