"""E-E-A-T trust signals — the SOP's Trust Gate, as free on-page heuristics.

Google (and AI answer engines) favour pages that show real Experience,
Expertise, Authoritativeness and Trust. None of this needs a vendor — it's all
detectable in the HTML: is there a named author, contact/NAP, policy links,
reviews/social proof, external validation, and citation-ready formatting. Pure
(HTML in, rows out).
"""
from __future__ import annotations

import re


from pipeline.scanner.rows import make_row
_row = make_row("eeat")


def _has(low: str, *needles: str) -> bool:
    return any(n in low for n in needles)


def eeat_rows(html: str) -> list[dict]:
    h = html or ""
    low = h.lower()
    schema = low.replace(" ", "").replace("'", '"')
    rows: list[dict] = []

    # Author / expertise — a named, credentialed author.
    author = ('"@type":"person"' in schema or re.search(r'rel=["\']author', low)
              or re.search(r'\b(written|reviewed|posted)\s+by\b', low)
              or re.search(r'class=["\'][^"\']*author', low))
    rows.append(_row("Author / expertise", "ok" if author else "warn",
                     "A named author signals expertise (E-E-A-T)." if author
                     else "No clear author/credentials — Google and AI trust anonymous content less.",
                     "passing" if author else 'add a named author with credentials + Person schema'))

    # Trust — contact / NAP present.
    contact = ("tel:" in low or "mailto:" in low
               or re.search(r"\b\d{2,4}[-\s.]\d{3,4}[-\s.]\d{3,4}\b", low)
               or '"@type":"postaladdress"' in schema)
    rows.append(_row("Contact / trust", "ok" if contact else "warn",
                     "Contact details (phone/email/address) signal a real business." if contact
                     else "No visible phone/email/address — a trust gap for users and Google.",
                     "passing" if contact else "show a phone, email and physical address"))

    # Policy links.
    policies = [p for p in ("privacy", "terms", "refund", "return policy", "disclaimer")
                if p in low]
    rows.append(_row("Policy links", "ok" if policies else "warn",
                     f"Trust policies linked ({', '.join(policies)})." if policies
                     else "No privacy/terms/refund links — expected trust signals, especially for YMYL.",
                     "passing" if policies else "link Privacy, Terms and (if selling) Refund policies",
                     detail=", ".join(policies)))

    # Social proof / reviews.
    proof = ('"@type":"review"' in schema or '"@type":"aggregaterating"' in schema
             or _has(low, "testimonial", "★", "customer review", "what our clients"))
    rows.append(_row("Social proof", "ok" if proof else "info",
                     "Reviews/testimonials present — real user validation." if proof
                     else "No visible reviews/testimonials — add real ones to build trust.",
                     "passing" if proof else "embed verified reviews/testimonials (+ Review schema)"))

    # Authoritativeness — external validation.
    authority = _has(low, "as featured in", "as seen in", "award", "accredited",
                     "certified", "trusted by", "featured on")
    rows.append(_row("Authoritativeness", "ok" if authority else "info",
                     "External validation (press/awards/accreditation) present." if authority
                     else "No 'as featured in' / awards / accreditations — external validation lifts authority.",
                     "passing" if authority else "add media badges, awards or accreditations if you have them"))

    # Citation-ready formatting — tables / Q&A / summaries AI can lift.
    citable = ("<table" in low or re.search(r"<h[23][^>]*>[^<]*\?", low)
               or "<strong" in low or "<b>" in low)
    rows.append(_row("Citation-ready formatting", "ok" if citable else "info",
                     "Tables / Q&A / bolded summaries make facts easy for Google and AI to lift." if citable
                     else "Little structured formatting — AI engines can't easily extract citable facts.",
                     "passing" if citable else "add comparison tables, Q&A blocks and bolded key facts"))
    return rows
