---
name: pw
description: Use this skill when Codex needs to browse or automate websites with the user's real Safari session, including logged-in pages, Keychain autofill, Touch ID, JavaScript-rendered pages, screenshots, downloads, form fills, clicks, scraping, and web workflows where normal HTTP fetches are insufficient. Backed by the local safari-pw CLI.
metadata:
  short-description: Automate the user's real Safari browser
---

# Safari `pw`

Use the local `pw` CLI when a task needs browser interaction through the user's real Safari profile: authenticated sites, Keychain/Touch ID flows, JavaScript-rendered pages, form submission, screenshots, links/text extraction, downloads, or workflows that need browser state.

The command should already be on `PATH` as `pw`. If it is missing, check `/Users/alex/Code/safari-pw/pw` and `/Users/alex/.local/bin/pw`.

## First Checks

- Run `pw doctor` if Safari automation fails or permissions are unknown.
- Run `pw` with no arguments for the full command reference.
- Every agent task must use its own named session, such as `--name codex-parking-20260822-0915`. Do not reuse a generic shared session when tasks may overlap.
- At the start of a task, run `pw cleanup --stale-hours 12` to collect sessions left by interrupted work.

## Common Commands

```bash
pw cleanup --stale-hours 12
pw nav URL --name codex-task-20260822-0915
pw snap --name codex-task-20260822-0915
pw text [SELECTOR] --name codex-task-20260822-0915
pw links [SELECTOR] --name codex-task-20260822-0915
pw html [SELECTOR] --name codex-task-20260822-0915
pw click SELECTOR --name codex-task-20260822-0915
pw fill SELECTOR TEXT --name codex-task-20260822-0915
pw press Enter --name codex-task-20260822-0915
pw screenshot /tmp/pw-screenshot.png --name codex-task-20260822-0915
pw wait SELECTOR --name codex-task-20260822-0915
pw back --name codex-task-20260822-0915
pw close --name codex-task-20260822-0915
pw close --all
```

Selectors can be CSS selectors or `text=...` for visible text.

Use `pw batch` for several browser actions in one connection:

```bash
pw batch --name codex "nav https://example.com" "click 'text=Sign in'" "snap"
```

## Workflow

1. Navigate with `pw nav URL --name codex`; it prints title, URL, and visible text.
2. Use `pw snap --name codex` to inspect the current page before deciding the next action.
3. Use `pw links --name codex` when choosing navigation targets.
4. Use `pw screenshot PATH --name codex` only when visual layout matters; inspect the image with the local image viewer if needed.
5. Use `pw wait SELECTOR --name codex` after actions that trigger async page updates.
6. **Mandatory cleanup:** before sending the final response, run `pw close --name SESSION` on success, failure, timeout, or a blocked workflow. Treat it like a `finally` block. Do not preserve a browser session unless the user explicitly asks; authenticated cookies remain in Safari without keeping the task window open.
7. Verify cleanup with `pw tabs --name SESSION`; it must report `No tabs for current pw session.` If close fails, retry once and report the cleanup failure rather than silently leaving a window behind.

`pw close --all` closes every pw-owned window and scrubs all pw state. Use it only for an intentional global reset after confirming no other automation task is active; never use it as routine per-task cleanup.

## Framework-Specific Commands

Some apps ignore ordinary synthetic DOM events.

- React/MUI: try `pw react-click SELECTOR --name codex` or `pw react-set SELECTOR onChange VALUE --name codex`.
- AngularJS 1.x: try `pw ng-click SELECTOR --name codex` or `pw ng-set SELECTOR VALUE --name codex`.

## Downloads And Trusted Clicks

Use `pw download SELECTOR_OR_URL --to PATH --name codex` for authenticated downloads.

If Safari blocks the first download from an origin, the user may need to allow downloads in Safari settings. For native trusted clicks, `PW_ALLOW_FOREGROUND=1` may be required because Safari must briefly become frontmost.

## Boundaries

- Use web search or HTTP fetches for simple public facts and static pages.
- Use Playwright or another browser tool for Chromium-only sites, CI, cross-browser testing, or isolated browser profiles.
- Avoid `pw eval JS` with untrusted input; it runs JavaScript in the user's real browser session.
