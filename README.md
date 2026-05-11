# safari-pw

**Use your real Safari from the CLI: existing cookies, Keychain autofill, Touch ID, no focus stealing.**

**For CI, use Playwright. For your actual browser, use `pw`.**

```bash
curl -fsSL https://raw.githubusercontent.com/alexbw/safari-pw/main/pw \
  -o /usr/local/bin/pw && chmod +x /usr/local/bin/pw
pw doctor                          # check Safari permissions
pw nav https://news.ycombinator.com
pw click "text=newest"
pw screenshot /tmp/hn.png
```

One Python file. No dependencies. No browser binaries to install.

---

## Why

Playwright/Puppeteer/Selenium automate a fresh browser profile. `pw` automates the Safari you already use. That means your cookies, Keychain passwords, Touch ID prompts, and existing sessions all work. It also runs in the background, so Safari doesn't yank focus while scripts run.

## Things this unlocks

- **Screenshot a dashboard you're already logged into.** No re-auth. No headless profile.
- **Submit a form behind Okta / Google SSO / 2FA without re-implementing auth.** Touch ID prompts pop up; Keychain fills them.
- **Let an AI agent use the web as you, not as a blank browser.** Claude Code, Cursor, MCP — any tool that can shell out gets web access with your real identity.
- **Run scripts while you're in another app.** Safari does the work in the background; nothing steals focus.

## Where it's the wrong tool

- **CI / cross-browser testing.** Use Playwright. This is macOS + Safari only by design.
- **Chrome-only sites.** A handful refuse Safari; fall back to Playwright for those.
- **Massively parallel scraping.** Fine for a dozen concurrent named sessions, not a thousand.

## Install

Requires macOS and Python 3.8+ (which ships with macOS).

```bash
# One-liner: drop it on your PATH
curl -fsSL https://raw.githubusercontent.com/alexbw/safari-pw/main/pw \
  -o /usr/local/bin/pw && chmod +x /usr/local/bin/pw

# Or clone and symlink:
git clone https://github.com/alexbw/safari-pw.git
ln -s "$PWD/safari-pw/pw" /usr/local/bin/pw
```

Then run the one-time setup check:

```bash
pw doctor
```

It will tell you which (if any) Safari permissions you need to enable. There are three:

1. **Safari → Settings → Advanced → "Show features for web developers"**
2. **Safari → Settings → Developer → "Allow JavaScript from Apple Events"**
3. The first time you run `pw`, macOS will ask: *"Terminal wants to control Safari."* Click OK.

That's it. No Homebrew tap, no `pip install`, no browser download.

### Installing the `/pw` skill for Claude Code

The repo ships a slash-command skill at [`skill/pw.md`](skill/pw.md). To install it for Claude Code:

```bash
# Symlink into ~/.claude/commands (slash commands live here)
ln -s "$PWD/safari-pw/skill/pw.md" ~/.claude/commands/pw.md

# Or copy if you'd rather not symlink
cp safari-pw/skill/pw.md ~/.claude/commands/pw.md
```

Restart Claude Code (or open a new session) and `/pw` will appear in the skill list. The skill assumes `pw` is on your `PATH` — verify with `which pw`.

### Installing for Codex CLI

Codex doesn't have a built-in slash-command directory the way Claude Code does, but it picks up tool guidance from `AGENTS.md` files. Either:

- Add a section to your project's `AGENTS.md` (or `~/.codex/AGENTS.md` for global) pointing at the `pw` binary and summarizing common commands, or
- Paste the contents of `skill/pw.md` (stripping the frontmatter) into your project `AGENTS.md`.

Codex will then know to invoke `pw nav`, `pw snap`, etc. when it needs a browser.

### Other agents

The `skill/pw.md` body (frontmatter stripped) is plain instructional Markdown — drop it into any agent's system prompt, tool description, or context file. The CLI itself is provider-agnostic; the skill file just teaches an LLM when and how to call it.

## Usage

```bash
pw nav URL              # navigate; prints title, URL, and visible text
pw click SELECTOR       # CSS selector or `text=...`
pw fill SEL TEXT        # fill an input
pw type TEXT            # type into the focused element
pw press KEY            # Enter, Tab, Escape, ArrowDown, ...
pw select SEL VALUE     # pick from a dropdown
pw screenshot [PATH]    # screenshot the page (default /tmp/pw-screenshot.png)
pw snap                 # title + URL + visible text in one call
pw text [SEL]           # visible text (full page or selector)
pw html [SEL]           # innerHTML
pw links [SEL]          # all links on the page
pw eval JS              # run arbitrary JavaScript, print the result
pw wait SEL             # wait up to 10s for a selector to appear
pw tabs                 # list open tabs
pw tab N                # switch to tab N
pw back                 # go back
pw close                # close pw's tracked tab (or scrub state)
pw status               # is Safari running?
pw doctor               # check setup
pw batch "CMD1" "CMD2" ...   # run multiple commands in one connection (faster)
```

Run `pw` with no arguments for the full reference.

### Output flags

`nav`, `click`, and `back` automatically print the resulting page text. Override with:

```bash
pw nav example.com --quiet              # navigate only
pw nav example.com --links              # print links instead of text
pw nav example.com --html "main"        # print HTML of <main>
```

### Multi-agent / multi-tab sessions

Each `--name` tracks its own tab independently. Use this when running multiple agents or scripts that shouldn't fight over the same tab:

```bash
pw nav https://site-a.com --name alice
pw nav https://site-b.com --name bob
pw click "#submit" --name alice         # targets site-a tab
pw fill "#input" "hi" --name bob        # targets site-b tab
```

You can also set `PW_SESSION=alice` in the environment.

### React / MUI sites

Some React apps ignore synthetic DOM clicks. For those, `pw` can invoke React fiber handlers directly:

```bash
pw react-click "button.complicated"
pw react-set "input.controlled" onChange "new value"
```

### Talking to Safari is slow — batch when you can

Each `pw` invocation pays a ~50-150 ms round-trip for `osascript`. If you're chaining several actions, `batch` runs them in one connection:

```bash
pw batch \
  "nav https://example.com" \
  "click 'text=More information'" \
  "screenshot /tmp/result.png"
```

## How it works

`pw` is a thin Python wrapper around `osascript -l JavaScript`. Apple's JXA bridge lets you call Safari's scripting interface (open URLs, list tabs, switch tabs) and — crucially — `safari.doJavaScript(...)` to evaluate arbitrary JS in any tab. That's enough to build a Playwright-style API.

Screenshots use macOS's native `screencapture -l<windowID>`, which reads from the window-server backing store. That's why it works even when Safari is occluded or fully behind another app.

The whole thing is one Python file, ~2300 lines, stdlib only. No async, no event loop, no driver protocol. If something breaks, you can fix it.

## Designed for AI agents

`pw` was built to give Claude Code (and similar LLM agents) a way to use the web with your real identity. A few choices that come from that:

- **Terse, deterministic output** — `nav` prints title + URL + the first 200 lines of visible text, which is usually exactly what an LLM needs to decide its next action. No accessibility-tree dump, no JSON envelope.
- **`snap`** — a single `osascript` round-trip that returns title + URL + body text. Great when an agent just wants to know "what's on this page right now?"
- **`batch`** — pipeline several commands in one connection so an agent can plan multiple steps without paying the JXA round-trip per step.
- **Named sessions** — multiple agents can run concurrently without stomping on each other's tabs.
- **Background by default** — when an agent runs `pw screenshot`, Safari does not pop to the front and disrupt what you were doing.

If you're building a Claude Code skill, MCP server, or Cursor plugin that needs web access with the user's real session: `pw` is probably the smallest dependency you can pull in.

## Safety and security

A few things to be aware of, since this is automating a browser with your real cookies:

- **`pw eval JS` runs arbitrary JavaScript in the current tab** — that's intentional and powerful. Don't pipe untrusted input into it.
- **State files** (which Safari tab `pw` is tracking) live under `~/Library/Application Support/safari-pw/` with `0700` directory and `0600` file permissions. Not in `/tmp`.
- **Session names** (`--name`, `PW_SESSION`) are validated against `[A-Za-z0-9._-]{1,64}` to prevent path traversal.
- **Screenshot paths** are normalized to absolute paths before being passed to `screencapture`, so a `-`-prefixed filename can't be misinterpreted as a flag.

If you find a real security bug, please open a private security advisory on GitHub rather than a public issue.

## FAQ

**Why not Playwright with `channel: "webkit"`?**
That gives you WebKit, not Safari. No Keychain, no synced cookies, no Touch ID, no extensions, separate profile. The whole point of `pw` is *your real Safari*.

**Why not Chrome with `--user-data-dir=$HOME/.../Chrome`?**
Possible, but you have to quit your real Chrome first (the profile lock), it foregrounds windows aggressively, and you don't get Keychain integration. Also: Safari is the default browser on a lot of Macs.

**Will this work on iPhone / iPad?**
No. JXA only exists on macOS. Sorry.

**Linux?**
No. macOS only.

**Why is it written in Python instead of Swift / TypeScript / Bun?**
Because Python ships with macOS, has no install step, and has `subprocess` + `json` in the stdlib — which is literally all this needs. One file, zero deps, runs anywhere a Mac runs.

**Will it work with Safari Technology Preview?**
The script targets `Application("Safari")`. STP is a separate app (`Application("Safari Technology Preview")`). PRs welcome.

## Contributing

Bug reports, fixes, and small features welcome. Please:

- Keep the dependency footprint at zero. Stdlib only. This is a hard rule.
- Keep it one file. The whole appeal is "drop one script on your PATH."
- Add a short repro for any bug you fix, even just a comment in the PR.

## License

MIT — see [LICENSE](LICENSE).

## Credits

Built originally as a tool inside [Claude Code](https://claude.com/claude-code) skills, then carved out as a standalone project. Inspired by [Playwright](https://playwright.dev), but designed for the opposite half of the problem space: not "automate a clean browser for tests," but "automate the browser you already use."
