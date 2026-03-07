# Raspberry Pi Voice Input Milestone

## What this prototype does
This first checkpoint is a terminal-based Python app for Raspberry Pi 4 Model B that:

1. Records a short microphone clip locally on the Pi (`arecord`)
2. Saves it as a temporary WAV file
3. Sends the WAV file to OpenAI speech-to-text
4. Sends the transcript to an OpenAI text model
5. Prints transcript and assistant response
6. Speaks the assistant response through a configurable ALSA output device (`espeak-ng` + `aplay`)
7. Loops until you type `q` or `quit`

This is intentionally a simple sequential flow (no realtime streaming, no WebSockets, no GUI).

## Why this is the right first milestone
It validates the core input pipeline end-to-end with minimal moving parts:

`Mic on Pi -> local WAV -> OpenAI transcription -> OpenAI response -> terminal output`

If this works reliably, later robot features (buttons, speakers, movement, exhibit routing, realtime modes) are much easier to add.

## Hardware assumptions
- Raspberry Pi 4 Model B running Linux
- One microphone input path:
  - USB microphone, or
  - Pi-compatible microphone module recognized as an ALSA input device
- Internet access for OpenAI API calls

## Project structure
```text
.
├── .env.example
├── README.md
├── requirements.txt
└── voice_milestone.py
```

## Raspberry Pi / Linux prerequisites
Install system packages:

```bash
sudo apt update
sudo apt install -y alsa-utils python3-venv espeak-ng bluez
```

Quick TTS test on current default output:

```bash
espeak-ng "Speaker test on Raspberry Pi"
```

## Pair a Bluetooth speaker (headless)
Start Bluetooth service:

```bash
sudo systemctl enable --now bluetooth
```

Pair and connect speaker (replace `AA:BB:CC:DD:EE:FF`):

```bash
bluetoothctl
power on
agent on
default-agent
scan on
# wait until you see your speaker MAC, then:
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
exit
```

List playback devices and note the Bluetooth ALSA name:

```bash
aplay -L
```

Set the output device for TTS in your current shell:

```bash
export TTS_OUTPUT_DEVICE="bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp"
```

If your Bluetooth stack routes audio as default already, keep:

```bash
export TTS_OUTPUT_DEVICE="default"
```

## Verify microphone detection
List capture hardware devices:

```bash
arecord -l
```

List ALSA PCM device names:

```bash
arecord -L
```

If your mic appears in `arecord -l`, note its card/device numbers (for example `card 1, device 0` -> `hw:1,0`).

## Manual local recording test (before Python)
Default device test:

```bash
arecord -f S16_LE -r 16000 -c 1 -d 5 test_mic.wav
aplay test_mic.wav
```

Specific device test (example `hw:1,0`):

```bash
arecord -D hw:1,0 -f S16_LE -r 16000 -c 1 -d 5 test_mic.wav
aplay test_mic.wav
```

If playback is silent or fails, fix ALSA/mic setup first.

## Python environment setup
Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configure `OPENAI_API_KEY`
Create your `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and set your key.
You can also set `TTS_OUTPUT_DEVICE` there.

Load it into your shell:

```bash
set -a
source .env
set +a
```

Verify:

```bash
echo "${OPENAI_API_KEY:0:10}..."
echo "$TTS_OUTPUT_DEVICE"
```

## Configure microphone device (optional)
In `voice_milestone.py`, set `AUDIO_DEVICE`:

- `AUDIO_DEVICE = None` uses system default ALSA capture device
- `AUDIO_DEVICE = "hw:1,0"` forces a specific input device

Keep `RECORD_SECONDS`, `SAMPLE_RATE`, and `CHANNELS` in the constants section for easy tuning.

## Run the milestone
```bash
python voice_milestone.py
```

Expected loop:
- Press Enter to record a ~5s clip
- Transcript prints
- Assistant response prints and is spoken
- Repeat until `q` / `quit`

## Troubleshooting
### No mic detected
```bash
arecord -l
```
- If no capture devices are listed, check wiring/USB connection.
- For USB mics, replug and run `lsusb`.
- Restart Pi and retest.

### ALSA errors
- Confirm `arecord` exists:
  ```bash
  which arecord
  ```
- Inspect named devices:
  ```bash
  arecord -L
  ```
- Try explicit device (`hw:x,y`) in script constant `AUDIO_DEVICE`.
- If permission issues appear, add user to `audio` group and relog:
  ```bash
  sudo usermod -aG audio "$USER"
  ```

### Silent recordings
- Open mixer and check capture gain / mute:
  ```bash
  alsamixer
  ```
- Select correct sound card in `alsamixer` (`F6`), ensure capture channel is enabled.
- Retest manually with `arecord ...` and `aplay ...` before running Python.

### API key issues
- Ensure `OPENAI_API_KEY` is exported in current shell:
  ```bash
  echo "$OPENAI_API_KEY"
  ```
- If empty, reload `.env`:
  ```bash
  set -a
  source .env
  set +a
  ```

### OpenAI request failures
- Confirm internet access from Pi.
- Confirm key is valid and has API access.
- If model access differs on your account, change `TRANSCRIPTION_MODEL` or `RESPONSE_MODEL` constants in `voice_milestone.py`.

### No speech output from assistant response
- Confirm the speaker is connected:
  ```bash
  bluetoothctl info AA:BB:CC:DD:EE:FF
  ```
- Confirm output device name exists:
  ```bash
  aplay -L
  ```
- Test TTS and output path directly:
  ```bash
  espeak-ng --stdout "This is a test" > /tmp/tts_test.wav
  aplay -D "$TTS_OUTPUT_DEVICE" /tmp/tts_test.wav
  ```
- If needed, disable TTS by setting `TTS_ENABLED = False`.

## Future extensions (after this checkpoint)
1. Button-triggered recording (GPIO input)
2. Speaker output with text-to-speech
3. Exhibit-specific knowledge prompts/context injection
4. Robot movement integration on fixed route
5. Realtime voice conversation in a later phase (once basic pipeline is stable)
