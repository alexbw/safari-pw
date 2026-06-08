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
- Prefer named sessions for agent work: add `--name codex` or set `PW_SESSION=codex` so other sessions are not disturbed.

## Common Commands

```bash
pw nav URL --name codex
pw snap --name codex
pw text [SELECTOR] --name codex
pw links [SELECTOR] --name codex
pw html [SELECTOR] --name codex
pw click SELECTOR --name codex
pw fill SELECTOR TEXT --name codex
pw press Enter --name codex
pw screenshot /tmp/pw-screenshot.png --name codex
pw wait SELECTOR --name codex
pw back --name codex
pw close --name codex
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
6. Use `pw close --name codex` when done with a managed tab unless preserving state is useful.

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
