"""Source-code audit (pipeline/scanner/source_audit.py) — pure analyzer, offline."""
from pipeline.scanner.source_audit import analyze_source, fetch_repo_files


def test_next_is_ssr_ok():
    files = {"package.json": '{"dependencies":{"next":"14.0.0","react":"18"}}'}
    by = {r["what"]: r for r in analyze_source(files)}
    assert by["Source: rendering"]["severity"] == "ok" and "Next.js" in by["Source: rendering"]["detail"]


def test_cra_is_csr_error():
    files = {"package.json": '{"dependencies":{"react-scripts":"5.0.0"}}'}
    by = {r["what"]: r for r in analyze_source(files)}
    assert by["Source: rendering"]["severity"] == "error"


def test_vite_spa_warns():
    files = {"package.json": '{"devDependencies":{"vite":"5.0.0"}}'}
    by = {r["what"]: r for r in analyze_source(files)}
    assert by["Source: rendering"]["severity"] == "warn"


def test_robots_and_sitemap_from_repo():
    files = {"package.json": '{"dependencies":{"next":"14"}}',
             "public/robots.txt": "User-agent: *", "public/sitemap.xml": "<urlset></urlset>"}
    by = {r["what"]: r for r in analyze_source(files)}
    assert by["Source: robots.txt"]["severity"] == "ok"
    assert by["Source: sitemap.xml"]["severity"] == "ok"


def test_local_path_repo_fetches_nothing():
    assert fetch_repo_files("/Users/both/site", "tok") == {}
    assert fetch_repo_files("", "tok") == {}


def test_fetch_uses_injected_getter():
    def fake(url, token):
        return '{"dependencies":{"next":"14"}}' if url.endswith("package.json") else None
    files = fetch_repo_files("owner/name", "tok", fetch=fake)
    assert "package.json" in files
    assert analyze_source(files)  # analyzes cleanly
