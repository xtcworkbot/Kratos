# Telegram setup

Private Telegram chat with Kratos, running Claude Code in this folder. macOS only (uses launchd). Name, model and effort live in `bot.json`.

## What it does
- Owner-only private chat. Messages from anyone else, groups and forwarded impersonation are ignored.
- Text, images, uploaded video clips (up to 20 MB) and public video links.
- Each message runs Claude Code headless in this folder with AGENTS.md and NOW.md loaded fresh, plus WebSearch, WebFetch and sandboxed Bash.
- Streams the reply into one Telegram message. Replies over ~3,900 characters arrive as a .md file.
- Commands: /start, /help, /status, /stop, /new (/reset), /watch, /check.

## Safety limits built in
- Bash runs in the OS sandbox: reads only this project, can't write to Telegram/, AGENTS.md or CLAUDE.md, can't reach localhost. No unsandboxed fallback.
- File tools are restricted to the project. Inherited hooks, skills, MCP servers and other environment credentials are stripped.
- A job stops after 60 model turns, 120 tool calls, the 4th identical call, 5 consecutive tool errors or 30 minutes. /stop kills the whole process group.
- No automatic retries. If the bot restarts mid-task, the task is marked interrupted, not replayed.
- Token and chat state are stored outside the repo at `~/Library/Application Support/kratos-telegram/` (mode 0700). Logs: `~/Library/Logs/kratos-telegram/`.

## Install on a new Mac
1. Install Homebrew, then: `brew install python ffmpeg yt-dlp`
2. Install Claude Code and log in once interactively (`claude`, then `/login`). The bot uses that login. The runner uses flags such as `--safe-mode`, `--restricted` and `--permission-prompts`; check `claude --help` lists them on the new machine.
3. `python3 -m pip install -r Telegram/requirements.txt`
4. Optional, for videos without captions:
   ```
   python3 -m venv ~/Library/Application\ Support/kratos-telegram/watch-venv
   ~/Library/Application\ Support/kratos-telegram/watch-venv/bin/pip install faster-whisper
   ```
5. In Telegram, message @BotFather, `/newbot`, copy the token. Get your numeric user ID from @userinfobot.
6. From the project root: `python3 Telegram/telegram_bot.py --setup`. Paste the token (hidden), enter your ID, press Start in the bot chat when asked. This saves credentials privately and installs the launchd service `com.kratos.telegram`, which starts at login and restarts if it crashes.
7. Check: `python3 Telegram/telegram_bot.py --check`, then send `/status` and `/check` in Telegram.

## Run tests
`python3 Telegram/test_telegram_bot.py`

## Operate
- Restart: `launchctl kickstart -k gui/$(id -u)/com.kratos.telegram`
- Stop: `launchctl bootout gui/$(id -u)/com.kratos.telegram`
- Logs: `tail -f ~/Library/Logs/kratos-telegram/listener.err`
- Rename the bot: edit `bot.json` before running --setup. The slug sets the private folder, logs and service label.

## Limits
- The Mac must be awake, online and logged in, and the Claude login must be valid.
- Sandbox is not a VM. Don't give it wallets, payment access or real account credentials.
- Private or login-only video links need the clip uploaded instead.
