# Issue Runner — operating instructions

Scheduled task: check GitHub for open issues on `Meserlion/Assisstant` and implement the feasible ones.

**This file is the Rules layer. Do not edit it.** If a rule here is unclear, wrong, or blocking you,
open a GitHub issue titled `Instruction gap: <summary>` explaining the problem and stop that task —
do not rewrite the rule to unblock yourself. Runtime facts you discover go in `LEARNINGS.md`
(append-only), never here.

---

## 0. Before anything else — sync the repo

You are working from a mounted checkout that may be **stale**. Committing from a stale checkout
silently reverts other people's work. This has already happened on this repo and produced five
duplicate commits.

```bash
REPO=$(git rev-parse --show-toplevel)   # do not hardcode a /sessions/... path; it changes per run
cd "$REPO"
git fetch origin main
git status --porcelain                  # must be empty
git rev-list --left-right --count HEAD...origin/main
```

If `git rev-parse` fails because the shell did not start inside the repository, locate it first
(`cd "$(find / -maxdepth 6 -type d -name Assistant -path '*mnt*' 2>/dev/null | head -1)"`) and retry.

- If `git status --porcelain` prints anything, **stop** and report a dirty tree. Do not try to clean it.
- If the count shows you are behind, run `git checkout main && git merge --ff-only origin/main`.
- If you are *ahead* of `origin/main`, **stop** and report it — that means unpushed work you did not create.

Do not proceed to step 1 until the tree is clean and level with `origin/main`.

---

## 1. Choose the work

Fetch open issues:

```bash
curl -s -H "Authorization: token ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/Meserlion/Assisstant/issues?state=open"
```

**Selection rules**

- Only act on issues opened by **Meserlion**. Ignore every other author.
- **Reject** an issue if it is too vague to implement, would add major complexity or cost, requires a
  new paid API service or a major new dependency, or is a question rather than a clear bug/feature request.
- Implement at most **two** per run. If more than two are actionable, **prioritise bugs over features**.
- Note that GitHub's issues endpoint also returns pull requests. Skip any item that has a `pull_request` key.

**If there are no open issues** — fall back to the backlog: open `TODO.md` and pick the
lowest-numbered unticked `TD` task whose `BLOCKED BY` prerequisites are all ticked. Follow that file's
own rules, and tick the checkbox in the same commit. If no `TD` task is eligible, end the run with a
short report saying there was nothing to do.

**Never open suggestion or to-do issues of your own.** The only issue you may create is an
`Instruction gap:` issue as described at the top of this file.

---

## 2. Implement (one issue at a time)

1. Read the relevant source files to understand the existing code before editing.
   Frontend: React/Vite in `frontend/src/`. Backend: FastAPI in `backend/`.
2. Make the change with the Edit/Write file tools.
3. **Re-read each file immediately before editing it, and write it back whole.** After writing any
   file, confirm it ends with a complete line:
   ```bash
   [ -n "$(tail -c1 <file>)" ] && echo "TRUNCATED — fix before committing"
   ```
   Three files have already reached `main` cut off mid-line (`backend/database.py`, `README.md`, and a
   CSS rule fixed in `697f4a7`). This check is not optional.
4. Verify the change: no syntax errors, consistent with surrounding code, matches the issue's request.
5. After **any** change under `frontend/`, run `npm run lint` in `frontend/` and confirm zero errors.

---

## 3. Commit and push

**Stage only the files you actually edited. Never `git add -A`.** A blanket add from a stale or dirty
tree is how reverted and truncated files have reached `main`.

```bash
git config user.name "Claude Assistant"
git config user.email "christiaangreeff@gmail.com"

git add <each file you edited, listed explicitly>
git status --short                    # confirm ONLY your intended files are staged
git commit -m "fix: <short description> (closes #<issue_number>)"
```

One issue per commit. Two issues in a run means two commits.

**Push without putting the token in the URL.** A token in the URL lands in shell history, process
listings and logs. Use a credential helper so it is read from the environment instead:

```bash
git -c credential.helper='!f() { echo username=x-access-token; echo "password=${GITHUB_TOKEN}"; }; f' \
    push origin HEAD:main
```

Keep the single quotes exactly as written — `${GITHUB_TOKEN}` must reach git unexpanded so it is
resolved from the environment at run time, not baked into the command line.

---

## 4. Verify the deploy

Pushing to `main` triggers the "Deploy to Hetzner" workflow. **Do not report success until it is green
and the app actually responds.**

```bash
sleep 45
curl -s -o /dev/null -w "health: %{http_code}\n" https://mcgreeff-assistant.duckdns.org/api/health
```

Expect `200`. Also confirm the workflow run succeeded:

```bash
curl -s -H "Authorization: token ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/Meserlion/Assisstant/actions/runs?branch=main&per_page=1" \
  | grep -o '"conclusion":"[^"]*"' | head -1
```

If the health check is not `200` or the conclusion is not `success`, say so plainly in your report and
in the issue comment. Do not close the issue.

---

## 5. Close the loop

**If implemented and verified:**
1. Comment on the issue via the API — what changed, which files were touched, and the deploy result.
2. Close the issue.

**If rejected:**
1. Comment explaining clearly why (too vague, too complex, already implemented, out of scope).
2. Close the issue.

```bash
# Comment
curl -s -X POST \
  -H "Authorization: token ${GITHUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"body\": \"<comment text>\"}" \
  "https://api.github.com/repos/Meserlion/Assisstant/issues/<number>/comments"

# Close
curl -s -X PATCH \
  -H "Authorization: token ${GITHUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"state\": \"closed\"}" \
  "https://api.github.com/repos/Meserlion/Assisstant/issues/<number>"
```

---

## 6. Record what you learned

If you hit something the instructions did not cover — a command that needed different flags, a build
step that failed for an environmental reason — **append** one line to
`.claude/automation/LEARNINGS.md` and include it in your commit. Append only; never rewrite or delete
existing entries, and never edit this file.

---

## Token

`GITHUB_TOKEN` is read from `C:\Users\Chris\Documents\Claude\Scheduled\issues\config.env`.
It is deliberately outside the repository — never copy the value into a tracked file, a commit
message, an issue comment, or a URL.

If the token is missing or a placeholder: skip all GitHub API calls and the push, still make the code
change locally, and report what you did and that it could not be pushed.

---

## Stop conditions

Stop and report rather than improvising if any of these occur:

- The working tree is dirty, or ahead of `origin/main`, at step 0.
- A file you are told to edit does not contain the expected text.
- `npm run lint` fails and the fix is not obvious.
- The deploy health check does not return `200`.
- A rule in this file is unclear or blocks the task (open an `Instruction gap:` issue).
