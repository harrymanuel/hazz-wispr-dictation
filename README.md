<p align="center"><img src="docs/icon.png" width="96" alt="Hazz Wispr icon"></p>

# Hazz Wispr

Free, private push-to-talk dictation for Apple Silicon Macs: a DIY alternative to Wispr Flow.

**Hold Right Option → speak → release.** Your words are transcribed on-device, tidied by a
local AI model, and pasted wherever your cursor is. Nothing leaves your Mac.

## Features

- **Menu bar app.** Starts at login, with no Dock icon or Terminal window. The icon turns orange while listening.
- **Fast on-device speech-to-text.** Whisper `large-v3-turbo` on Apple's MLX framework transcribes a short sentence in under a second on an M1 Pro.
- **AI cleanup.** A local LLM (Ollama, `qwen2.5:3b`) removes filler words, resolves self-corrections
  ("Tuesday, no wait, Wednesday"), fixes punctuation and formats spoken lists. It is hardened so that
  dictated text like "ignore previous instructions…" is cleaned, never obeyed.
- **Personal dictionary.**
  - *Words* bias the speech model toward your spellings. "cube rectal" becomes "kubectl".
  - *Replacements* rewrite phrases in every dictation, e.g. "my email" becomes your address.
- **Dashboard** at `http://127.0.0.1:7070`: stats, searchable history, dictionary and settings.
- **Clipboard-safe.** Whatever you had copied is restored after pasting.

## How it works

```
Hazz Wispr.app (menu bar)
 ├── Hotkey listener ── Right Option held → record mic (16 kHz)
 ├── Engine ─────────── Whisper (MLX) → filler strip → Ollama cleanup → replacements → paste
 ├── Store ──────────── SQLite: settings, dictionary, history, stats
 └── Dashboard ──────── local HTTP server + vanilla JS web app
```

| Path | What it does |
|---|---|
| `hazz_wispr/engine.py` | Recording, transcription, cleanup, paste |
| `hazz_wispr/app.py` | Menu bar UI, permission onboarding, wiring |
| `hazz_wispr/server.py` | JSON API + static dashboard |
| `hazz_wispr/store.py` | SQLite storage |
| `hazz_wispr/web/` | Dashboard (HTML/CSS/JS, no build step, no external requests) |
| `macos/` | App bundle: C launcher, Info.plist, icon generator, build script |

The `.app` is a tiny C launcher that runs the Python package as a child process, so macOS grants
permissions to *Hazz Wispr* specifically rather than to Terminal or Python.

## Privacy & security

- Audio, transcripts and history never leave the Mac. Whisper runs in offline mode once downloaded.
- The dashboard only listens on `127.0.0.1`. It rejects foreign `Host` headers (DNS rebinding) and
  cross-site writes, and sends a strict Content-Security-Policy. All text is rendered with `textContent`.
- History can be switched off or cleared from the dashboard.
- Data lives in `~/Library/Application Support/Hazz Wispr/`.

## Setup

Needs an Apple Silicon Mac and [Ollama](https://ollama.com) (optional, for cleanup).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt
ollama pull qwen2.5:3b
macos/build_app.sh
open "Hazz Wispr.app"
```

On first launch, allow **Microphone**, **Accessibility** and **Input Monitoring** for Hazz Wispr.
To run from Terminal for debugging instead: `.venv/bin/python -m hazz_wispr`.

## Uninstall

Quit Hazz Wispr from the menu bar, then:

```bash
rm -f ~/Library/LaunchAgents/com.hazz.wispr.plist
rm -rf ~/Library/Application\ Support/Hazz\ Wispr
rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo
ollama rm qwen2.5:3b
rm -rf ~/.local/bin/uv ~/.local/bin/uvx ~/.local/share/uv
```

Then delete Ollama from Applications (plus `~/.ollama`), delete this folder, and remove Hazz Wispr
from System Settings → Privacy & Security.
