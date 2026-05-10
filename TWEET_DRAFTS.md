# Launch tweet drafts — for Alex's review

The repo URL will be `https://github.com/alexbw/safari-pw` (final once pushed).

---

## RECOMMENDED (codex-refined, 270 chars)

> Playwright is for clean browser automation. safari-pw is for the Safari you're actually logged into.
>
> Your cookies, Keychain autofill, and Touch ID work. It runs in the background, so it doesn't steal focus.
>
> One Python file. No deps. macOS only.
> https://github.com/alexbw/safari-pw

**Suggested first reply (to bump):**

> Install:
>
> ```
> curl -fsSL https://raw.githubusercontent.com/alexbw/safari-pw/main/pw -o /usr/local/bin/pw && chmod +x /usr/local/bin/pw
> ```
>
> Then run `pw doctor`.

**Suggested attached media:** a 5-10 second screen recording of `pw click` triggering a Touch ID prompt — that's the "wait, what?" moment that earns retweets.

---

## Original drafts (kept for reference)

---

## Draft A — single banger (264 chars)

> shipping a tiny thing: **safari-pw**
>
> a CLI that drives your real Safari from the terminal. your cookies, your Keychain, your Touch ID, all of it. runs in the background — no focus stealing.
>
> for CI use Playwright. for your actual browser, use this.
>
> one Python file, zero deps:
> github.com/alexbw/safari-pw

---

## Draft B — punchy hook + screenshot (~240 chars)

> Playwright automates a clean browser. **safari-pw** automates the Safari you're actually logged into.
>
> Keychain autofill works. Touch ID works. Background — no focus stealing.
>
> One Python file. No deps. macOS only.
>
> github.com/alexbw/safari-pw

*(attach: terminal screenshot of `pw nav … && pw click … && pw screenshot`, or a screen recording of a Touch ID prompt firing from a `pw` script)*

---

## Draft C — thread (4 tweets)

**1/**
> Open-sourcing a tiny thing I've been using daily: **safari-pw**.
>
> A CLI that drives the Safari you already use — with your cookies, your Keychain passwords, your Touch ID. In the background, no focus stealing.
>
> github.com/alexbw/safari-pw

**2/**
> Every browser-automation tool runs in a clean profile. Great for CI. Wrong for everything else.
>
> If you want to script your *real* browsing — log into the bank, scrape a SaaS dashboard you live in, automate something behind SSO — clean profiles force you to re-implement auth.

**3/**
> safari-pw uses Apple's JavaScript-for-Automation bridge to drive your actual Safari. Saved passwords autofill from Keychain. Touch ID prompts work. SSO sessions are right there.
>
> ```
> pw nav my-internal-dashboard.com
> pw screenshot /tmp/today.png
> ```

**4/**
> One Python file. Zero dependencies. Stdlib only. Built originally as a tool for Claude Code agents, but it's just a CLI — works fine from any shell script or any LLM tool that can shell out.
>
> Code, README, install in one line:
> github.com/alexbw/safari-pw

---

## Notes for Alex

- I picked the "for CI use Playwright, for your actual browser use pw" line because it's the clearest one-line positioning. Reuse it in any blog post.
- Best attached media is probably a 10-second screen recording showing a Touch ID prompt firing in response to a `pw click` — that's the wow moment that doesn't happen with Playwright.
- HN title suggestion: "safari-pw – Drive your real Safari from the CLI (with Keychain and Touch ID)"
