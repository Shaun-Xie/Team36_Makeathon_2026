#!/usr/bin/env python3
"""First working Raspberry Pi voice-input milestone."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
RESPONSE_MODEL = "gpt-4.1-mini"
RECORD_SECONDS = 5
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_DEVICE = None  # Example: "hw:1,0"
SYSTEM_PROMPT = (
    "You are an interactive educational guide for a zoo environment. "
    "Explain things clearly, briefly, and engagingly for general visitors. "
    "Focus on environmental awareness, ecology, conservation, animal habitats, "
    "biodiversity, pollution, climate impacts, and human interaction with ecosystems."
)


def check_api_key() -> str:
    """Return OPENAI_API_KEY or raise a clear error."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Missing OPENAI_API_KEY. Export it in your shell before running."
        )
    return api_key


def create_openai_client(api_key: str):
    """Create OpenAI client with current SDK style."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI Python package is not installed. Run: pip install -r requirements.txt"
        ) from exc

    return OpenAI(api_key=api_key)


def ensure_recorder_available(audio_device: Optional[str]) -> None:
    """Verify `arecord` exists and optional device configuration looks valid."""
    if shutil.which("arecord") is None:
        raise RuntimeError(
            "`arecord` was not found. Install ALSA utils: sudo apt install -y alsa-utils"
        )

    if audio_device:
        result = subprocess.run(
            ["arecord", "-L"], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or "Unknown error"
            raise RuntimeError(
                "Could not list recording devices with `arecord -L`.\n"
                f"arecord error: {stderr}"
            )

        # hw:x,y devices may not appear literally in `arecord -L`, so skip strict check there.
        if not audio_device.startswith("hw:") and audio_device not in result.stdout:
            raise RuntimeError(
                f"AUDIO_DEVICE '{audio_device}' not found in `arecord -L` output.\n"
                "Run `arecord -L` or set AUDIO_DEVICE to a valid value."
            )


def create_temp_wav_path() -> str:
    """Create a temp file path for a WAV recording."""
    temp_file = tempfile.NamedTemporaryFile(prefix="pi_voice_", suffix=".wav", delete=False)
    temp_path = temp_file.name
    temp_file.close()
    return temp_path


def record_audio(output_wav: str, seconds: int = RECORD_SECONDS) -> None:
    """Record local audio clip using arecord."""
    cmd = ["arecord", "-q"]
    if AUDIO_DEVICE:
        cmd.extend(["-D", AUDIO_DEVICE])
    cmd.extend(
        [
            "-f",
            "S16_LE",
            "-r",
            str(SAMPLE_RATE),
            "-c",
            str(CHANNELS),
            "-d",
            str(seconds),
            output_wav,
        ]
    )

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown arecord failure"
        lowered = stderr.lower()
        if "no such file" in lowered or "cannot find card" in lowered:
            raise RuntimeError(
                "Recording failed: microphone/device not found.\n"
                f"arecord error: {stderr}\n"
                "Use `arecord -l` to identify the correct capture device."
            )
        raise RuntimeError(f"Recording failed.\narecord error: {stderr}")

    wav_path = Path(output_wav)
    if not wav_path.exists():
        raise RuntimeError("Recording failed: WAV file was not created.")
    if wav_path.stat().st_size <= 44:
        raise RuntimeError("Recording appears empty (no audio frames in WAV file).")


def transcribe_audio(client, wav_path: str) -> str:
    """Send WAV file to OpenAI speech-to-text and return transcript text."""
    try:
        with open(wav_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model=TRANSCRIPTION_MODEL,
                file=audio_file,
            )
    except Exception as exc:
        raise RuntimeError(f"Failed transcription request: {exc}") from exc

    text = (getattr(transcript, "text", None) or "").strip()
    if not text:
        raise RuntimeError("Transcription returned empty text.")
    return text


def get_assistant_response(client, transcript: str) -> str:
    """Send transcript to text model and return assistant reply."""
    try:
        response = client.responses.create(
            model=RESPONSE_MODEL,
            instructions=SYSTEM_PROMPT,
            input=transcript,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed text model request: {exc}") from exc

    reply = (getattr(response, "output_text", None) or "").strip()
    if not reply:
        raise RuntimeError("Text model returned an empty response.")
    return reply


def cleanup_temp_file(path: str) -> None:
    """Best-effort temp file cleanup."""
    try:
        if path and Path(path).exists():
            os.remove(path)
    except OSError as exc:
        print(f"[WARN] Could not remove temp file {path}: {exc}")


def main_loop() -> int:
    """Interactive terminal loop."""
    try:
        api_key = check_api_key()
        client = create_openai_client(api_key)
        ensure_recorder_available(AUDIO_DEVICE)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print("Raspberry Pi Voice Input Milestone")
    print("----------------------------------")
    print(f"Recorder: arecord | Duration: {RECORD_SECONDS}s")
    print(f"Sample rate: {SAMPLE_RATE} Hz | Channels: {CHANNELS}")
    print(f"Audio device: {AUDIO_DEVICE or 'default'}")
    print("Press Enter to record, or type q / quit to exit.\n")

    while True:
        try:
            user_input = input("> ").strip().lower()
        except EOFError:
            print("\nInput closed. Exiting.")
            return 0

        if user_input in {"q", "quit"}:
            print("Exiting.")
            return 0
        if user_input:
            print("Press Enter to record, or type q / quit to exit.")
            continue

        wav_path = create_temp_wav_path()
        try:
            print(f"Recording {RECORD_SECONDS} seconds...")
            record_audio(wav_path, seconds=RECORD_SECONDS)

            print("Transcribing with OpenAI...")
            transcript = transcribe_audio(client, wav_path)
            print("\nTranscript:")
            print(transcript)

            print("\nGenerating assistant response...")
            response = get_assistant_response(client, transcript)
            print("\nAssistant response:")
            print(response)
            print()
        except RuntimeError as exc:
            print(f"[ERROR] {exc}\n")
        finally:
            cleanup_temp_file(wav_path)


if __name__ == "__main__":
    try:
        raise SystemExit(main_loop())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        raise SystemExit(0)
