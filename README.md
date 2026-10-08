# Kratos

A small AI workspace template for Claude Code and Codex, with a private Telegram bot. Shared rules, shared state, evidence on disk.

## Layout
```
AGENTS.md          canonical rules for every engine (fill in Identity, Focus)
CLAUDE.md          Claude Code entry point -> AGENTS.md + NOW.md
NOW.md             current state and handover between sessions
Research/          findings and sources, one file or folder per topic
Experiments/       prototypes and their actual results
Telegram/          bot transport, tests, video helper (see Telegram/SETUP.md)
.claude/           Claude Code project settings and skills
.agents/skills/    Codex project skills
.env.example       secret variable names; copy to .env (never committed)
```

## Start
1. Fill in Identity and Focus in AGENTS.md, and Direction in NOW.md.
2. `cp .env.example .env` if needed and add any keys locally.
3. Open the folder in Claude Code or Codex. Both read the same files.
4. Telegram bot: follow Telegram/SETUP.md.

## How it works
Every session reads AGENTS.md and NOW.md, does the work, and writes a short checkpoint back to NOW.md. Detail goes in Research/ or Experiments/. The Telegram bot runs the same rules from your phone, in a sandbox.
