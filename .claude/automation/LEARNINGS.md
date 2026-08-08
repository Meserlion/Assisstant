# Learnings

Runtime facts discovered by the scheduled issue runner. See `issue-runner.md` for the rules.

**Append only.** Add new entries at the bottom as `- YYYY-MM-DD — <what you learned>`. Never rewrite
or delete an existing entry, and never move a rule here into `issue-runner.md` or vice versa.

Good entries are concrete and reusable: a command that needed a different flag, a build step that
failed for an environmental reason, a path that turned out to be different than documented. Skip
anything specific to one issue — that belongs in the issue comment.

---

- 2026-08-08 — The mounted checkout can carry a stale index and leftover `.git/*.lock` files (one sat
  there for two months, freezing the repo). Cloning fresh into `/tmp` and working from that is more
  reliable than trying to sync the mount in place, and it makes `git add -A` accidents impossible.
  Push from the clone; the mount does not need to be touched at all.
- 2026-08-08 — The backend runs from a virtualenv: `systemd` calls
  `/opt/assistant/backend/venv/bin/uvicorn` (see `deploy.sh`). Any `pip install` on the server must
  use `/opt/assistant/backend/venv/bin/pip`, not bare `pip`, or the packages land in system Python
  and the service never sees them.
- Sandbox can't complete `npx playwright install chromium` (184 MB, no resume) within the 40s per-command cap, so the smoke suite can't run locally there. Mitigation: run `npm run lint` + `npm run build` locally (both must pass) and rely on the CI build-check gate, which runs the smoke test on push and blocks the deploy on failure.
