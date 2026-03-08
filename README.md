# Raspberry Pi Voice Input Milestone (OpenAI + ElevenLabs)

## What this prototype does
This terminal-based Raspberry Pi 4 app does:

1. Record a short local microphone clip with `arecord`
   - starts when speech is detected
   - stops after short silence
2. Transcribe it with OpenAI speech-to-text
3. Generate a response with an OpenAI model
4. Print transcript and assistant response
5. Synthesize assistant speech with ElevenLabs
6. Play synthesized audio through ALSA output (including Bluetooth speaker)

This remains a simple sequential flow (no realtime streaming, no WebSockets, no GUI).

## What changed in this refactor
- Replaced local `espeak-ng` synthesis with ElevenLabs Text-to-Speech API.
- Added `ELEVENLABS_API_KEY` environment variable support.
- Added ElevenLabs synthesis helpers:
  - `synthesize_speech(client, text)`
  - `play_audio_file(path)`
  - `speak_text(client, text)`
- Kept mic recording, OpenAI transcription, and OpenAI response flow unchanged.
- Kept printed assistant responses for debugging.
- Kept graceful behavior: if TTS setup/request/playback fails, text still prints.

## Project structure
```text
.
├── .env.example
├── README.md
├── requirements.txt
└── voice_milestone.py
```

## Raspberry Pi / Linux prerequisites
Install required system packages:

```bash
sudo apt update
sudo apt install -y alsa-utils python3-venv bluez
```

Notes:
- `arecord` and `aplay` come from `alsa-utils`.
- `bluez` is used to pair/connect Bluetooth speakers.

## Pair Bluetooth speaker (headless)
Start Bluetooth service:

```bash
sudo systemctl enable --now bluetooth
```

Pair and connect speaker:

```bash
bluetoothctl
power on
agent on
default-agent
scan on
# after you see your speaker MAC:
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
exit
```

List playback devices:

```bash
aplay -L
```

Use a Bluetooth ALSA device in `TTS_OUTPUT_DEVICE` (example):

```bash
export TTS_OUTPUT_DEVICE="bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp"
```

If your system already routes Bluetooth as default output:

```bash
export TTS_OUTPUT_DEVICE="default"
```

## Verify microphone detection
```bash
arecord -l
arecord -L
```

Manual recording test:

```bash
arecord -f S16_LE -r 16000 -c 1 -d 5 /tmp/test_mic.wav
aplay /tmp/test_mic.wav
```

## Python environment setup
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment variables
Create `.env` from example:

```bash
cp .env.example .env
```

Edit `.env` with:

```bash
OPENAI_API_KEY=your_openai_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
TTS_OUTPUT_DEVICE=default
```

Load variables:

```bash
set -a
source .env
set +a
```

Verify:

```bash
echo "${OPENAI_API_KEY:0:10}..."
echo "${ELEVENLABS_API_KEY:0:10}..."
echo "$TTS_OUTPUT_DEVICE"
```

## Run the app
```bash
python voice_milestone.py
```

Loop behavior:
- App listens for speech automatically
- Recording starts when speech is detected
- Recording stops after short silence
- Transcript prints
- Assistant response prints
- ElevenLabs audio plays
- Press `Ctrl+C` to exit

## Test ElevenLabs TTS path independently
Run this standalone test on the Pi:

```bash
python - <<'PY'
import os
import subprocess
from elevenlabs.client import ElevenLabs

voice_id = "on7De0nZUAc9uGezUxS6"
model_id = "eleven_turbo_v2_5"
output_format = "pcm_16000"
output_device = os.getenv("TTS_OUTPUT_DEVICE", "default")
api_key = os.getenv("ELEVENLABS_API_KEY")

if not api_key:
    raise SystemExit("Missing ELEVENLABS_API_KEY")

client = ElevenLabs(api_key=api_key)
audio = client.text_to_speech.convert(
    voice_id=voice_id,
    model_id=model_id,
    output_format=output_format,
    text="Hello from ElevenLabs on Raspberry Pi.",
)

path = "/tmp/elevenlabs_test.pcm"
written = 0
with open(path, "wb") as f:
    for chunk in audio:
        if chunk:
            f.write(chunk)
            written += len(chunk)

if written == 0:
    raise SystemExit("ElevenLabs returned empty audio")

cmd = ["aplay", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1"]
if output_device != "default":
    cmd += ["-D", output_device]
cmd.append(path)
subprocess.run(cmd, check=True)
print("Played:", path)
PY
```

## Troubleshooting
### Missing `ELEVENLABS_API_KEY`
```bash
echo "$ELEVENLABS_API_KEY"
```
If empty, reload `.env`:
```bash
set -a
source .env
set +a
```

### ElevenLabs package not installed
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Invalid voice/model settings
- Check `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`, and `ELEVENLABS_OUTPUT_FORMAT` in `voice_milestone.py`.
- If ElevenLabs rejects the request, the app prints a warning and continues with text output.

### Playback tool missing
```bash
which aplay
sudo apt install -y alsa-utils
```

### No audio output
```bash
aplay -L
```
- Confirm `TTS_OUTPUT_DEVICE` matches a valid playback device.
- Test direct playback:
```bash
aplay -D "$TTS_OUTPUT_DEVICE" -f S16_LE -r 16000 -c 1 /tmp/elevenlabs_test.pcm
```

### Network/API failure
- Confirm Pi internet connectivity.
- Confirm ElevenLabs/OpenAI API keys are valid.
- On failure, text output still appears so the conversation loop keeps working.

### No speech detected / keeps timing out
- Speak closer to the microphone and increase capture gain (`alsamixer`).
- Adjust VAD settings in `voice_milestone.py`:
  - `VAD_START_THRESHOLD_RMS` (lower it if normal speech is missed)
  - `VAD_END_SILENCE_SECONDS` (increase if recordings end too early)
  - `VAD_LISTEN_TIMEOUT_SECONDS` (increase if users pause before speaking)
  - `VAD_MAX_RECORD_SECONDS` (increase for longer questions)

## Future extensions
1. GPIO button-triggered recording
2. Exhibit-specific context injection
3. Route-based robot movement integration
4. Realtime voice in later phase after core pipeline is stable
