"""E-E-A-T checker: Experience, Expertise, Authoritativeness, Trust.

Google does not score E-E-A-T. Its Search Quality Rater Guidelines describe what
human raters look for, and pages about health (YMYL) are held to the strictest
standard. So this checks the signals a page can actually show, and every row
carries the evidence it was judged on: the author's name and title from the
schema, the citation's domain, the accreditation sentence, the rating and count.

It reads JSON-LD (through `@graph` and nested objects) rather than loose keyword
matches. The version it replaced passed "Social proof" on any page containing a
star character and "Authoritativeness" on the word "award".

Pure: HTML (+ the page URL) in, rows out. Stdlib only.
"""
from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urlsplit

PILLARS = ("Experience", "Expertise", "Authoritativeness", "Trust")

_MEDICAL_TYPES = {"hospital", "medicalorganization", "medicalclinic", "physician", "medicalwebpage",
                  "medicalbusiness", "dentist", "pharmacy", "diagnosticlab", "medicalcondition"}
_ORG_TYPES = {"organization", "localbusiness", "corporation", "ngo", "educationalorganization"} | _MEDICAL_TYPES
_AUTHORITATIVE = ("who.int", "nih.gov", "ncbi.nlm.nih.gov", "pubmed", "cdc.gov", "nhs.uk", "mayoclinic.org",
                  "cochrane.org", "thelancet.com", "nejm.org", "bmj.com", ".gov", ".edu", "moh.gov")
_ACCREDITATION = re.compile(
    r"(joint commission international|\bJCI\b|ISO\s?\d{4,5}|accredited by [^.<]{3,60}|"
    r"accreditation (?:from|by) [^.<]{3,60}|certified by [^.<]{3,60})", re.I)
_CREDENTIAL = re.compile(r"\b(MD|M\.D\.|MBBS|FRCS|FRCP|PhD|DDS|DMD|RN|PharmD|FACS|FACC)\b")


# ── parsing ──────────────────────────────────────────────────────────────────

def jsonld_objects(html: str) -> list[dict]:
    """Every JSON-LD object on the page, flattened through @graph, lists and
    nested values, each with a lowercased `@types` set added. Broken blocks are
    skipped, never raised."""
    out: list[dict] = []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = {str(x).lower() for x in (t if isinstance(t, list) else [t]) if x}
            if types:
                out.append({**node, "@types": types})
            for k, v in node.items():
                if k != "@types":
                    walk(v)

    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html or "", re.I | re.S):
        try:
            walk(json.loads(block.strip()))
        except (ValueError, TypeError):
            continue
    return out


def _text(html: str) -> str:
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.I | re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def _snippet(text: str, m: re.Match, width: int = 70) -> str:
    s = text[max(0, m.start() - 10): m.end() + width - (m.end() - m.start())]
    return s.strip()[:width]


def _names(v) -> list[str]:
    items = v if isinstance(v, list) else [v]
    return [str(i.get("name") if isinstance(i, dict) else i).strip() for i in items if i]


def _sameas(obj: dict) -> list[str]:
    v = obj.get("sameAs")
    return [s for s in (v if isinstance(v, list) else [v]) if isinstance(s, str) and s.startswith("http")]


def _row(key: str, pillar: str, label: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": f"eeat.{key}", "what": f"{pillar} · {label}", "why": why,
            "fix": "passing" if severity == "ok" else fix, "detail": detail, "severity": severity}


# ── the checker ──────────────────────────────────────────────────────────────

def eeat_rows(html: str, url: str = "") -> list[dict]:
    h = html or ""
    low = h.lower()
    text = _text(h)
    objs = jsonld_objects(h)
    types = set().union(*(o["@types"] for o in objs)) if objs else set()
    medical = bool(types & _MEDICAL_TYPES) or bool(
        re.search(r"\b(hospital|clinic|patients?|doctors?|physicians?|surgery|medical)\b", text, re.I))
    must = "warn" if medical else "info"     # YMYL pages are held to the stricter bar
    rows: list[dict] = []

    persons = [o for o in objs if "person" in o["@types"] and o.get("name")]
    orgs = [o for o in objs if o["@types"] & _ORG_TYPES and o.get("name")]
    pages = [o for o in objs if o["@types"] & {"webpage", "medicalwebpage", "article", "newsarticle", "blogposting"}]

    # ── Experience ──
    story = re.search(r"(patient (?:story|stories|experience)|case stud(?:y|ies)|testimonial|"
                      r"in (?:my|our) experience|success stor(?:y|ies))", text, re.I)
    rows.append(_row("first_hand", "Experience", "First-hand stories", "ok" if story else "info",
                     "Patient stories, case studies or first-hand accounts show real experience." if story
                     else "No patient stories, case studies or first-hand accounts found.",
                     "add real patient stories or case studies (with consent)",
                     _snippet(text, story) if story else ""))

    dated = [o for o in pages + orgs if o.get("dateModified") or o.get("lastReviewed")]
    visible_date = re.search(r"(last (?:updated|reviewed)|updated on|reviewed on)[:\s]+[^.<]{4,30}", text, re.I)
    fresh = dated or visible_date
    detail = ""
    if dated:
        d = dated[0]
        detail = f"dateModified {d.get('dateModified') or '-'}, lastReviewed {d.get('lastReviewed') or '-'}"
    elif visible_date:
        detail = visible_date.group(0)[:50]
    rows.append(_row("freshness", "Experience", "Last updated date", "ok" if fresh else must,
                     "The page says when it was last updated or reviewed." if fresh
                     else "No 'last updated' date on the page or in the schema; readers and raters cannot tell if it is current.",
                     "show 'Last updated <date>' and set dateModified in the page schema", detail))

    # ── Expertise ──
    byline = re.search(r"\b(written|reviewed|posted|authored)\s+by\s+([A-Z][^.<,]{2,50})", text) \
        or re.search(r'rel=["\']author|class=["\'][^"\']*\b(author|byline)\b', low)
    rows.append(_row("author_byline", "Expertise", "Author byline", "ok" if byline else must,
                     "A named author is visible on the page." if byline
                     else "No visible author name on the page.",
                     "add a visible 'Written by <name, credentials>' byline",
                     byline.group(0)[:60] if byline and byline.lastindex else ""))

    author = next((p for p in persons if p.get("jobTitle")), persons[0] if persons else None)
    rows.append(_row("author_schema", "Expertise", "Author in schema", "ok" if author else must,
                     "The page's schema names a person with their role." if author
                     else "No Person in the page schema, so search engines cannot tie the content to a qualified author.",
                     "add a Person (name, jobTitle) as the page author in JSON-LD",
                     f"{author.get('name')}" + (f" ({author.get('jobTitle')})" if author and author.get("jobTitle") else "")
                     if author else ""))

    cred_schema = next((p for p in persons if p.get("honorificSuffix") or p.get("hasCredential")), None)
    cred_text = _CREDENTIAL.search(text)
    creds = cred_schema or cred_text
    rows.append(_row("credentials", "Expertise", "Credentials", "ok" if creds else must,
                     "Professional credentials are stated." if creds
                     else "No credentials (MD, FRCS, PhD...) stated for the people behind the content.",
                     "state credentials in the byline and in Person.honorificSuffix / hasCredential",
                     (f"{cred_schema.get('name')}: {cred_schema.get('honorificSuffix') or 'hasCredential'}"
                      if cred_schema else _snippet(text, cred_text, 40)) if creds else ""))

    with_sameas = next((p for p in persons if _sameas(p)), None)
    rows.append(_row("author_sameas", "Expertise", "Author profiles linked", "ok" if with_sameas else "info",
                     "The author's schema links to external profiles, so identity can be verified." if with_sameas
                     else "The author's schema links to no external profile (LinkedIn, medical council registry).",
                     "add Person.sameAs links to the author's verifiable profiles",
                     f"{with_sameas.get('name')}: {urlsplit(_sameas(with_sameas)[0]).netloc}" if with_sameas else ""))

    if medical:
        reviewed = next((o for o in objs if o.get("reviewedBy") or o.get("lastReviewed")), None)
        visible_review = re.search(r"medically reviewed by\s+[^.<]{3,60}", text, re.I)
        ok = reviewed or visible_review
        rows.append(_row("medical_review", "Expertise", "Medically reviewed", "ok" if ok else "warn",
                         "The page states it was medically reviewed, and by whom." if ok
                         else "Health content with no medical reviewer named; raters hold medical pages to the highest bar.",
                         "add 'Medically reviewed by <name, credentials>' and MedicalWebPage.reviewedBy / lastReviewed",
                         (", ".join(_names(reviewed.get("reviewedBy"))) or f"lastReviewed {reviewed.get('lastReviewed')}")
                         if reviewed else (visible_review.group(0)[:60] if visible_review else "")))

    # ── Authoritativeness ──
    org = orgs[0] if orgs else None
    rows.append(_row("org_schema", "Authoritativeness", "Organization in schema", "ok" if org else "warn",
                     "The site identifies the organization behind it in schema." if org
                     else "No Organization / Hospital schema identifying who publishes the site.",
                     "add Organization (or Hospital) JSON-LD with name, url, address",
                     f"{sorted(org['@types'] & _ORG_TYPES)[0].title()}: {org.get('name')}" if org else ""))

    org_sa = next((o for o in orgs if _sameas(o)), None)
    rows.append(_row("org_sameas", "Authoritativeness", "Organization profiles linked", "ok" if org_sa else "info",
                     "The organization's schema links to its external profiles." if org_sa
                     else "The organization's schema links to no external profile (Wikipedia, Google, social).",
                     "add Organization.sameAs links (Wikipedia, Wikidata, official social pages)",
                     ", ".join(urlsplit(s).netloc for s in _sameas(org_sa)[:3]) if org_sa else ""))

    acc = _ACCREDITATION.search(text)
    rows.append(_row("accreditation", "Authoritativeness", "Accreditations named", "ok" if acc else "info",
                     "A named accreditation or certification is stated." if acc
                     else "No named accreditation or certifying body found (a star rating or the word 'award' is not one).",
                     "name each accreditation and its body (e.g. 'Accredited by Joint Commission International, 2021') and link the certificate",
                     _snippet(text, acc) if acc else ""))

    links = re.findall(r'href=["\'](https?://[^"\']+)', h, re.I)
    site = urlsplit(url).netloc.lower().removeprefix("www.")
    cited = sorted({urlsplit(l).netloc.lower().removeprefix("www.") for l in links
                    if any(a in l.lower() for a in _AUTHORITATIVE)
                    and urlsplit(l).netloc.lower().removeprefix("www.") != site})
    rows.append(_row("citations", "Authoritativeness", "Authoritative sources cited",
                     "ok" if cited else "info",
                     "The page links to authoritative sources." if cited
                     else "No links to authoritative sources (WHO, PubMed, government health bodies).",
                     "cite and link the guidelines or studies the content relies on",
                     ", ".join(cited[:4])))

    about = re.search(r'href=["\']([^"\']*/(?:about|about-us|who-we-are))(?=[/"\'?#])', h, re.I)
    rows.append(_row("about_page", "Authoritativeness", "About page linked", "ok" if about else "warn",
                     "The page links to an About page." if about else "No link to an About page explaining who runs the site.",
                     "link an About page from the header or footer", about.group(1)[:60] if about else ""))

    # ── Trust ──
    if url:
        https = url.lower().startswith("https://")
        rows.append(_row("https", "Trust", "HTTPS", "ok" if https else "error",
                         "Served over HTTPS." if https else "Served over plain HTTP.",
                         "serve every page over HTTPS", urlsplit(url).scheme))

    tel = re.search(r'href=["\']tel:([^"\']+)', h, re.I)
    mail = re.search(r'href=["\']mailto:([^"\'?]+)', h, re.I)
    addr = next((o for o in objs if "postaladdress" in o["@types"]), None)
    found = [x for x in (f"tel {tel.group(1)}" if tel else "", f"email {mail.group(1)}" if mail else "",
                         f"address {addr.get('streetAddress') or addr.get('addressLocality')}" if addr else "") if x]
    rows.append(_row("contact", "Trust", "Contact details", "ok" if found else "warn",
                     "Real contact details are on the page." if found
                     else "No phone link, email link or PostalAddress schema on the page.",
                     "add a tel: link, a contact email and PostalAddress schema", ", ".join(found)[:80]))

    policies = sorted({m.lower() for m in re.findall(r'href=["\'][^"\']*(privacy|terms|cookie|disclaimer)', h, re.I)})
    need = {"privacy", "terms"}
    rows.append(_row("policies", "Trust", "Policy pages linked", "ok" if need <= set(policies) else "warn",
                     "Privacy and terms pages are linked." if need <= set(policies)
                     else "Privacy and/or terms pages are not linked from the page.",
                     "link Privacy Policy and Terms from the footer", ", ".join(policies)))

    if medical:
        disc = re.search(r"(not (?:a )?substitute for (?:professional )?medical advice|"
                         r"for informational purposes only|consult (?:your|a) (?:doctor|physician)|medical disclaimer)", text, re.I)
        rows.append(_row("medical_disclaimer", "Trust", "Medical disclaimer", "ok" if disc else "warn",
                         "The page carries a medical disclaimer." if disc
                         else "Health content with no medical disclaimer.",
                         "add 'This information is not a substitute for professional medical advice.'",
                         _snippet(text, disc) if disc else ""))

    rating = next((o for o in objs if "aggregaterating" in o["@types"]), None)
    reviews = [o for o in objs if "review" in o["@types"]]
    if rating:
        try:
            value = float(str(rating.get("ratingValue")))
            count = rating.get("reviewCount") or rating.get("ratingCount")
            valid = 0 < value <= float(rating.get("bestRating") or 5) and count is not None and int(str(count)) > 0
        except (TypeError, ValueError):
            valid, value, count = False, rating.get("ratingValue"), rating.get("reviewCount")
        rows.append(_row("reviews", "Trust", "Reviews", "ok" if valid else "warn",
                         "Review rating markup is present and well-formed." if valid
                         else "AggregateRating markup is present but ratingValue / reviewCount are missing or invalid.",
                         "give AggregateRating a numeric ratingValue and a reviewCount from real, verifiable reviews",
                         f"rating {value} from {count} reviews"))
    else:
        rows.append(_row("reviews", "Trust", "Reviews", "ok" if reviews else "info",
                         "Individual reviews are marked up." if reviews
                         else "No review or rating markup found (visible stars alone are not verifiable).",
                         "mark up real reviews with Review / AggregateRating schema",
                         f"{len(reviews)} Review object(s)" if reviews else ""))
    return rows
