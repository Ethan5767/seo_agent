"""Gap -> Draft via the `claude` CLI on the user's subscription (no API key, no
per-token cost). build_prompt and parse_result are pure; the subprocess is the
only side effect and is injectable as `run` so the suite runs offline.

The CLI returns an outer JSON envelope whose `.result` is the model's text. We
ask the model for a compact JSON object {title, body, brand_mention}; parse_result
unwraps the envelope, strips any ```json fence, and json.loads the inner text."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from pipeline.seed.gaps import Gap


@dataclass
class Draft:
    gap: Gap
    title: str
    body: str
    brand_mention: str


def build_prompt(gap: Gap) -> str:
    return (
        "You are an SEO content writer. Write one platform-appropriate post that "
        "naturally mentions a brand, to seed brand presence where it is currently "
        "absent.\n\n"
        f"Brand: {gap.brand}\n"
        f"Platform: {gap.platform}\n"
        f"Topic: {gap.topic}\n"
        f"Target keyword: {gap.target_keyword}\n"
        f"Angle: {gap.angle}\n"
        f"Brand URL to link: {gap.url_target}\n\n"
        "The post must read as genuinely useful, not an ad. Mention the brand once, "
        "in context, with the URL. Weave in the target keyword naturally.\n\n"
        "Output ONLY a JSON object, no prose, with exactly these keys:\n"
        '{"title": "...", "body": "markdown body", '
        '"brand_mention": "the single sentence that cites the brand + URL"}'
    )


def parse_result(raw: str) -> dict:
    try:
        envelope = json.loads(raw)
        text = envelope["result"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ValueError(f"unparseable claude envelope: {e}")
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fence
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        inner = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"claude result is not JSON: {e}")
    if not all(k in inner for k in ("title", "body", "brand_mention")):
        raise ValueError(f"claude result missing keys: {inner.keys()}")
    return inner


def _run_claude(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:200]}")
    return proc.stdout


def draft(gap: Gap, run=None) -> Draft:
    run = run or _run_claude
    inner = parse_result(run(build_prompt(gap)))
    return Draft(gap=gap, title=inner["title"], body=inner["body"],
                 brand_mention=inner["brand_mention"])
