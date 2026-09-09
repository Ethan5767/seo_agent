"""`printf ... | grep -q` under `set -o pipefail` is a false-failure generator.

grep -q exits at the first match; the writer then dies of SIGPIPE (or reports
`write error: Broken pipe`), and pipefail hands that non-zero back as the
pipeline's status. The `|| { ... fail=1; }` guard fires on a page that HAS the
tag. It is racy on body size, so it false-failed a different subset of lee's
routes every night for a week before anyone read the log. See B-043.

Use a here-string (`grep -q PAT <<<"$body"`) — no pipe, no writer to kill.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted(Path(".github/workflows").glob("*.yml"))
PIPED_QUIET_GREP = re.compile(r"\|\s*grep\s+-[a-zA-Z]*q")


def test_there_are_workflows_to_check():
    assert WORKFLOWS


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_quiet_grep_on_the_right_of_a_pipe(wf):
    text = wf.read_text()
    if "pipefail" not in text:
        pytest.skip(f"{wf.name} does not set pipefail")
    hits = [
        f"{wf.name}:{i}: {line.strip()}"
        for i, line in enumerate(text.splitlines(), 1)
        if PIPED_QUIET_GREP.search(line.split("#", 1)[0])
    ]
    assert not hits, (
        "`grep -q` on the right of a pipe under pipefail reports a false "
        "failure when the match IS found. Use a here-string:\n  " + "\n  ".join(hits))
