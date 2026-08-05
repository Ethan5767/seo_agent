"""seo-content-pipeline — the shared automation engine.

Subpackages:
    lib      shared helpers (config loading, client profile, curl, topology)
    gates    build-time quality gates (the 21-check suite)
    deploy   post-deploy submission + live verification
    intake   DOCX / Google Drive intake tooling
    audit    live-site audits, preflight, and one-off setup tools

Client configuration is never stored here (Model A: it lives in each client's
own repo). Every tool takes the client project directory as an argument.
"""

__version__ = "2.0.0"
