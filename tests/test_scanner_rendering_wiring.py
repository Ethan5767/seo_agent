"""The scanner has one authoritative CSR verdict: Technical, not SEO."""
from pipeline.scanner import server


def test_scanner_emits_one_technical_csr_verdict_not_a_duplicate_seo_row():
    html = "<html><head><script src='/app.js'></script></head><body><div id='root'></div></body></html>"

    def fetch(_url):
        return html, 200, "", None

    report = server.build_report("https://x.com/", fetch=fetch, crux=None,
                                 selected={"seo", "tech"})
    assert "health.csr_empty_shell" not in {r["code"] for r in report["seo"]}
    rendering = [r for r in report["tech"] if r["what"] == "Rendering (crawler-visible content)"]
    assert len(rendering) == 1
    assert rendering[0]["detail"] == "likely CSR shell — heuristic"
