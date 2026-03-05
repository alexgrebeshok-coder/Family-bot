# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

### Personal Rules
- If user sends an audio/voice message, transcribe it with whisper-cpp (whisper-cli) by default.

### Telegram Bot API
- **Bot Token:** `8345979333:AAHLchSF4rxNrNMFQ9oZM1GFZqCWrpd1st8`
- **Bot Name:** @KrabikkBot
- **Chat ID (Саша):** 1258992460
- **API Base:** `https://api.telegram.org/bot<TOKEN>/`

### TTS (Text-to-Speech)
- **Edge TTS** — основной (бесплатно)
  - Voice: `ru-RU-DmitryNeural` (мужской)
  - Команда: `python3 -m edge_tts --voice ru-RU-DmitryNeural --text "..." --write-media output.mp3`
- **Конвертация в OGG:** `ffmpeg -i input.mp3 -c:a libopus -b:a 64k output.ogg`

---

Add whatever helps you do your job. This is your cheat sheet.
