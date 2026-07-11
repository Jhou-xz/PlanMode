# Plan Mode

Plan Mode is a personal AI assistant delivered as a Discord bot. It understands text, voice, and image messages; extracts reminders, ideas, and queries; stores everything in PostgreSQL; and chats back in the same language you use.

## What is Plan Mode

- A Discord DM bot that acts as a daily companion.
- Remembers facts, preferences, goals, and routines about you.
- Schedules reminders and fires them via DM at the right time.
- Generates a daily summary at a configurable time in your timezone.
- Builds a weekly schedule PNG (Monday-Sunday) on request.
- Transcribes voice messages locally using faster-whisper.
- Understands images with DeepSeek multimodal support plus OCR fallback.

## Required accounts and API keys

- **Discord bot token** — create a bot at https://discord.com/developers/applications and enable the Message Content and DM Intents.
- **DeepSeek API key** — sign up at https://platform.deepseek.com.
- **PostgreSQL database** — local or managed.

## Local development setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env with your keys
python scripts/init_db.py
python main.py
```

## Environment variables

```bash
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DATABASE_URL=postgresql+asyncpg://planmode:password@localhost:5432/planmode
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
SUMMARY_DEFAULT_TIME=22:00
```

## Discord bot setup

1. Create an application at https://discord.com/developers/applications.
2. Add a Bot user.
3. Under **Privileged Gateway Intents**, enable:
   - Message Content Intent
   - (DM messages are handled automatically by the default intents.)
4. Copy the bot token into `.env` as `DISCORD_BOT_TOKEN`.
5. Use the OAuth2 URL generator with the `bot` scope and no special permissions (DMs only need the bot token).
6. Send the bot a direct message to start.

## Example interactions

**Text reminder**
```
Remind me to call David tomorrow at 4pm
```

**Voice message**
Send a voice message: "I need to buy milk tomorrow morning."

**Image message**
Send a photo of a receipt or handwritten note.

**Query**
```
What do I have scheduled this week?
```

**Weekly schedule image**
```
Show me my schedule
```

## VPS deployment with `deploy/setup.sh`

1. Copy the project to `/opt/plan-mode` on your VPS.
2. Place a valid `.env` file at `/opt/plan-mode/.env`.
3. Run the setup script as root:
   ```bash
   sudo bash deploy/setup.sh
   ```
4. Check the service status:
   ```bash
   sudo systemctl status plan-mode
   sudo journalctl -u plan-mode -f
   ```

The systemd service will restart the bot automatically on failure and start it on boot.

## Troubleshooting

- **Bot does not respond to DMs:** Verify the Discord bot token and that Message Content Intent is enabled.
- **Database errors:** Ensure PostgreSQL is running and the `DATABASE_URL` in `.env` is correct.
- **Voice transcription fails:** Check that `ffmpeg` is installed and the faster-whisper model is downloaded.
- **Timezone not recognized:** Users must reply with a valid IANA timezone such as `America/New_York` or `Asia/Shanghai`.
- **Images not understood:** Ensure DeepSeek API key is valid; the bot falls back to OCR if available (`tesseract-ocr` is installed by `setup.sh`).
