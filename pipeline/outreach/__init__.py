"""Backlink outreach — the SOP §12 add-on, up to (not including) the send.

Three pure-ish units and a CLI orchestrator:

    qualify   the 4-point safety check before a domain enters the bank
    linkbank  the candidate store in the CLIENT repo (docs/outreach/linkbank.json)
    content   tier-1 / tier-2 draft generation via the `claude` CLI
    run       wf-outreach: qualify -> bank -> draft; prints a summary, NEVER sends

The actual outreach email to a site owner is a HUMAN step by design (SOP §12:
"requires human outreach"), so nothing here transmits anything.
"""
