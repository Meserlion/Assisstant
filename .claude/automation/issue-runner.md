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
- **Reject** an issue if it would add major complexity or cost, requires a new paid API service or a
  major new dependency, or is a question rather than a request.
- **Ask** (see below) if the issue is a genuine request but you cannot tell exactly what to change.
- Implement at most **two** per run. If more than two are actionable, **prioritise bugs over features**.
- Note that GitHub's issues endpoint also returns pull requests. Skip any item that has a `pull_request` key.

### Before implementing, check the request is safe to take literally

Read the code you would be changing **before** deciding the issue is actionable. Ask yourself: does
the thing I am about to change also do something the issue never mentions?

**If carrying out the request literally would remove or break functionality the issue says nothing
about, do not implement it and do not guess the intent. Ask instead.**

Worked example: an issue saying "remove the header, it just takes space" sounds trivial, but
`<header>` in `frontend/src/App.jsx` also contains the tab navigation and the report button.
Deleting it literally would leave the app with no way to change tabs and no way to report the
breakage. The right response is to ask which part should go, not to pick one.

This matters because the automated checks will not catch it. The deploy health check only tests
`/api/health`, which is the backend — a completely broken frontend still returns 200 and the run
still reports success. You are the only check on this. Be deliberate.

Bias: when implementing would be destructive and irreversible for the user, asking costs one run.
Guessing wrong can ship a broken app that nothing detects.

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
6. After any change under `frontend/`, also run the smoke tests — see below.

### The frontend deploy gate

`frontend/tests/smoke.spec.js` loads the built app in a real browser and asserts the shell is
intact: `#root` renders, no uncaught page errors, all four tab buttons and the report button exist,
and each tab activates when clicked. It runs in `build-check`, which `deploy` depends on, so
**a failure blocks the deploy entirely.**

Run it before you push:

```bash
cd frontend
npx playwright install chromium    # first run only
npm run build
npm run test:smoke
```

**If the smoke tests fail and you did not intend to change the app's structure, the gate is doing
its job — your change is wrong. Fix the code.**

**If the issue genuinely asks you to change that structure** — move the tabs to the bottom bar,
rename a tab, remove the report button — then update `frontend/tests/smoke.spec.js` in the **same
commit** so it asserts the new intended structure. A shell change and its test change belong
together; splitting them means one commit deploys with a stale gate.

> **Never delete, skip, or weaken an assertion just to make the tests pass.** If a test blocks you
> and you cannot tell whether the structure change is intended, that is exactly the case for asking
> on the issue (step 5) rather than editing the test. Removing an assertion to get green silently
> removes the only check that would catch a broken frontend — `/api/health` returns 200 regardless.

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

There are **three** outcomes. Only two of them close the issue.

**If implemented and verified:**
1. Comment on the issue via the API — what changed, which files were touched, and the deploy result.
2. Close the issue.

**If rejected** (too complex, too costly, needs a paid service, already implemented, or a question):
1. Comment explaining clearly why.
2. Close the issue.

**If it needs clarification — do NOT close it:**
1. Comment with a *specific* question, not "please clarify". State what you found in the code, what
   the ambiguity is, and offer the concrete options. For example:

   > The `<header>` also contains the tab navigation (Notes / Merge / Ask / Calendar) and the report
   > button, so removing it entirely would leave no way to switch tabs or report problems. Which did
   > you mean?
   > 1. Remove only the "Assistant" title, keep the tabs and report button
   > 2. Remove the title and move the tabs to the bottom bar
   > 3. Something else

2. **Leave the issue open.** Do not implement anything. Do not close it.
3. Move on to the next issue.

**Never ask the same question twice.** Before commenting, fetch the issue's existing comments:

```bash
curl -s -H "Authorization: token ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/Meserlion/Assisstant/issues/<number>/comments"
```

If the most recent comment is your own clarifying question and the issue author has not replied
since, **skip this issue entirely this run** — say so in your report and move on. If the author has
replied, use that answer and implement.

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
- The frontend smoke tests fail and you did not intend to change the app's structure.
- You are tempted to delete or weaken a smoke-test assertion to get a green run.
- The deploy health check does not return `200`.
- A rule in this file is unclear or blocks the task (open an `Instruction gap:` issue).
- Carrying out an issue literally would break something the issue does not mention — ask on the
  issue and leave it open (see step 5), rather than picking an interpretation.
- You are unsure whether a change is destructive. Asking costs one run; guessing wrong can ship a
  broken app that no automated check detects.
