# Admin Checklist — human-only setup

Things the pipeline cannot do for itself. Each section records what a human
must configure by hand and its current status. Update this file in the same
commit as any change that alters what a human must do (see `CLAUDE.md` §2).

| # | Item | Status |
|---|---|---|
| 1 | GitHub org/repos created; engine repo tagged; client repos call workflows `@tag` | ☐ |
| 2 | Branch protection on client repo default branches (needs a paid GitHub plan on private repos — without it gates report but cannot block) | ☐ |
| 3 | Deploy platform projects + secrets on each client repo | ☐ |
| 4 | `DISCORD_BOT_TOKEN` secret on this repo; bot invited with View + Read Message History on the content category only | ☐ |
| 5 | Drive OAuth (read-only) bootstrap run; `DRIVE_*` secrets set | ☐ |
| 6 | `PIPELINE_DRIVE_PARENT_FOLDER_ID` secret set | ☐ |
| 7 | `CLIENT_REPOS_TOKEN` fine-grained PAT minted by the org owner: client repos only, Contents + Pull requests + Actions R/W; stored as a secret on this repo. Enables the PR-only handoff stage — without it the stage skips green | ☐ |
| 8 | Analytics/GSC access per client for the audit modules | ☐ |
