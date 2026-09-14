# AGENTS.md — seo_agent (Antigravity & Agentic Pair Programming)

This repository follows the sync and engineering contracts documented in [`CLAUDE.md`](./CLAUDE.md).

## Critical Operating Rules

1. **Thermonuclear Review (`/thermonuclear`)**:
   - When executing any task-by-task plan, pause and run a **Thermonuclear Code Quality Review** after **every 3rd task** (tasks 3, 6, 9, …) before continuing.
   - Whenever the user types `/thermonuclear`, mentions `/thermonuclear`, or asks for a code quality audit, immediately execute the strict maintainability standards defined in [`.agents/skills/thermonuclear/SKILL.md`](./.agents/skills/thermonuclear/SKILL.md).
   - Core standards:
     - Rule 0: Ambitious structural simplification ("code judo" moves).
     - Rule 1: Do not let files grow over 1,000 lines without strong structural decomposition.
     - Rule 2: Zero ad-hoc conditionals / spaghetti branching.
     - Rule 3: Bias toward cleaner design, not just working code.
     - Rule 4: Direct, boring, maintainable code over magic abstractions.
     - Rule 5: Strict type and boundary cleanliness.
     - Rule 6: Use canonical layers and helpers.
     - Rule 7: Parallelize independent work; ensure atomic state updates.

2. **DataForSEO Live Spend** (the 2026-09-09 freeze was lifted by the operator on 2026-09-14):
   - The test suite is hermetic and never calls DataForSEO (`tests/conftest.py` blocks sockets). Keep it that way.
   - A live call is spend. Make one only to prove a change, one tool at a time, and report the cost the scanner printed. The account balance is small.
   - `DATAFORSEO_PAUSE_SPEND=1` in the repo-root `.env` refuses every paid call. Check it before any live run.

3. **Privacy & Trust**:
   - Never commit or render real personal emails (use `you@example.com` or configured user email).
   - Never claim automated fixes are applied when they are merely staged.
   - Clearly label sample or demo data in UI metrics.

4. **Verification & Proof**:
   - Run tests directly and verify actual exit codes (`npm test`, `next build`, `pytest`).
   - Keep documentation synchronized in `CHANGELOG.md` under `[Unreleased]`.
