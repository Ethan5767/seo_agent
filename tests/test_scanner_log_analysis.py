from pipeline.scanner.log_analysis import analyze_logs, parse_access_logs, verify_bot_ip


def test_parse_common_and_json_access_logs():
    common = '66.249.66.1 - - [16/Sep/2026:10:00:00 +0000] "GET /about HTTP/1.1" 200 123 "-" "Googlebot/2.1"'
    cloudflare = '{"ClientIP":"157.55.39.1","Datetime":"2026-09-16T10:01:00Z","ClientRequestURI":"/robots.txt","EdgeResponseStatus":200,"UserAgent":"bingbot"}'
    entries = parse_access_logs(common + "\n" + cloudflare)
    assert len(entries) == 2
    assert entries[0].bot_name == "googlebot"
    assert entries[1].bot_name == "bingbot"


def test_reverse_dns_requires_forward_confirmation():
    assert verify_bot_ip("66.249.66.1", lambda _ip: ["crawl.googlebot.com"], lambda _name: ["66.249.66.1"])
    assert not verify_bot_ip("66.249.66.1", lambda _ip: ["evil.example"], lambda _name: ["203.0.113.1"])


def test_log_analysis_reports_frequency_waste_and_directory_budget():
    entries = parse_access_logs("\n".join(
        f'66.249.66.1 - - [16/Sep/2026:10:00:0{i} +0000] "GET {path} HTTP/1.1" {status} 123 "-" "Googlebot/2.1"'
        for i, (path, status) in enumerate((("/", 200), ("/filter?color=red", 200), ("/missing", 404)))
    ))
    rows = analyze_logs(entries, verify=lambda _ip, _bot: True, crawl_urls={"/"})
    codes = {row["code"] for row in rows}
    assert {"logs.crawl_frequency", "logs.crawl_waste", "logs.bot_response_codes", "logs.directory_budget"} <= codes
