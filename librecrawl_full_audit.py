#!/usr/bin/env python3
"""LibreCrawl Full Site Audit CLI.

Direct alias to test_librecrawl_engine.py.
Usage:
  python librecrawl_full_audit.py [URL] [--pages N] [--workers W]
Example:
  python librecrawl_full_audit.py https://www.oriendainternationalhospital.com.kh --pages 50
  python librecrawl_full_audit.py https://www.oriendainternationalhospital.com.kh --pages all
"""
from test_librecrawl_engine import main

if __name__ == "__main__":
    main()
