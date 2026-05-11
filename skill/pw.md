---
name: pw
description: "Browser automation via Safari (with Keychain autofill / Touch ID support). Use whenever interacting with web pages — navigation, clicking, form fills, screenshots, scraping, login flows, web research that needs JS-rendered content. Far more token-efficient than the Playwright MCP. Backed by the open-source safari-pw CLI."
---

# /pw — Safari Browser Automation

Use the `pw` CLI for any browser interaction. It controls Safari via JXA in the background (Safari does not need to be foregrounded), supports macOS Keychain autofill and Touch ID, and is far more token-efficient than the Playwright MCP.

**Source of truth:** [safari-pw on GitHub](https://github.com/alexbw/safari-pw). The `pw` binary must be on your `PATH`.

For Chromium-only sites, fall back to the Playwright MCP plugin.

## Discover usage

Run `pw` with no arguments to print the full command reference. Common commands:

- `pw nav URL` — navigate (auto-prints page text)
- `pw click SELECTOR` — CSS or `text=...`
- `pw fill SELECTOR TEXT` — fill input
- `pw type TEXT` / `pw press KEY` — typing / key events
- `pw snap` — fast page state (title + URL + visible text in one call)
- `pw text [SEL]` / `pw html [SEL]` / `pw links [SEL]` / `pw eval JS`
- `pw screenshot [PATH]` — defaults to `/tmp/pw-screenshot.png`
- `pw wait SELECTOR` — up to 10s
- `pw batch "CMD1" "CMD2" ...` — multiple commands in one connection (faster)
- `pw react-click SEL` / `pw react-set SEL PROP VALUE` — for MUI/React internals
- `pw tabs` / `pw tab INDEX` / `pw back` / `pw close` / `pw status`

Output flags on `nav`, `click`, `back`: `--links`, `--html`, `--quiet` (default auto-prints page text).

## Multi-agent sessions

Use `--name SESSION` (or `PW_SESSION` env var) to track separate tabs per agent:

```
pw nav https://site-a.com --name agent1
pw nav https://site-b.com --name agent2
pw click "#btn" --name agent1
```

## First-run setup

1. Safari → Settings → Advanced → "Show features for web developers"
2. Safari → Settings → Developer → "Allow JavaScript from Apple Events"
3. First run: approve "Terminal wants to control Safari" dialog
4. Run `pw doctor` to verify

## Notes

- Screenshots and `type`/`press` run fully in the background by default. If a site ignores synthetic events (rare), set `PW_KEYSTROKE=1` for OS-level keystrokes (activates Safari, needs Accessibility permission).
- `react-click` / `react-set` invoke React component handlers directly, bypassing the DOM event system — works for MUI/React even when DOM clicks don't.
