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
USE_GPIO_BUTTON = False
BUTTON_GPIO_PIN = 18
BUTTON_BOUNCE_TIME = 0.10
TTS_ENABLED = True
TTS_COMMAND = "espeak-ng"
TTS_RATE = 165
TTS_OUTPUT_DEVICE = os.getenv("TTS_OUTPUT_DEVICE", "default")
# Example Bluetooth ALSA device (if available): bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp
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


def ensure_tts_available() -> None:
    """Verify local text-to-speech command exists when enabled."""
    if not TTS_ENABLED:
        return
    if shutil.which(TTS_COMMAND) is None:
        raise RuntimeError(
            f"`{TTS_COMMAND}` was not found. Install it with: sudo apt install -y espeak-ng"
        )
    if shutil.which("aplay") is None:
        raise RuntimeError(
            "`aplay` was not found. Install ALSA utils: sudo apt install -y alsa-utils"
        )
    if TTS_OUTPUT_DEVICE and TTS_OUTPUT_DEVICE != "default":
        result = subprocess.run(
            ["aplay", "-L"], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or "Unknown error"
            raise RuntimeError(
                "Could not list playback devices with `aplay -L`.\n"
                f"aplay error: {stderr}"
            )
        if not TTS_OUTPUT_DEVICE.startswith("hw:") and TTS_OUTPUT_DEVICE not in result.stdout:
            raise RuntimeError(
                f"TTS_OUTPUT_DEVICE '{TTS_OUTPUT_DEVICE}' not found in `aplay -L` output.\n"
                "Run `aplay -L` and set a valid playback device."
            )


def create_gpio_button(pin: int):
    """Create a GPIO button input using gpiozero."""
    try:
        from gpiozero import Button
    except ImportError as exc:
        raise RuntimeError(
            "gpiozero is not installed. Install with: pip install gpiozero "
            "or sudo apt install -y python3-gpiozero"
        ) from exc

    try:
        return Button(pin, pull_up=True, bounce_time=BUTTON_BOUNCE_TIME)
    except Exception as exc:
        raise RuntimeError(f"Failed to initialize GPIO button on pin {pin}: {exc}") from exc


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


def speak_text(text: str) -> None:
    """Speak assistant text using espeak-ng and play via a selected ALSA output device."""
    if not TTS_ENABLED:
        return
    tts_wav = None
    try:
        temp_file = tempfile.NamedTemporaryFile(
            prefix="tts_output_", suffix=".wav", delete=False
        )
        tts_wav = temp_file.name
        with temp_file:
            result = subprocess.run(
                [TTS_COMMAND, "--stdout", "-s", str(TTS_RATE), text],
                stdout=temp_file,
                stderr=subprocess.PIPE,
                text=False,
                check=False,
            )

        if result.returncode != 0:
            stderr = (
                result.stderr.decode("utf-8", errors="replace").strip()
                if result.stderr
                else "Unknown TTS synthesis error"
            )
            raise RuntimeError(f"TTS synthesis failed.\n{TTS_COMMAND} error: {stderr}")

        wav_path = Path(tts_wav)
        if not wav_path.exists() or wav_path.stat().st_size <= 44:
            raise RuntimeError("TTS synthesis failed: output WAV is empty.")

        playback_cmd = ["aplay", "-q"]
        if TTS_OUTPUT_DEVICE and TTS_OUTPUT_DEVICE != "default":
            playback_cmd.extend(["-D", TTS_OUTPUT_DEVICE])
        playback_cmd.append(tts_wav)

        playback = subprocess.run(playback_cmd, capture_output=True, text=True, check=False)
        if playback.returncode != 0:
            stderr = playback.stderr.strip() or "Unknown playback error"
            raise RuntimeError(
                "TTS playback failed while sending audio to output device.\n"
                f"aplay error: {stderr}"
            )
    finally:
        if tts_wav:
            cleanup_temp_file(tts_wav)


def cleanup_temp_file(path: str) -> None:
    """Best-effort temp file cleanup."""
    try:
        if path and Path(path).exists():
            os.remove(path)
    except OSError as exc:
        print(f"[WARN] Could not remove temp file {path}: {exc}")


def run_interaction_cycle(client) -> None:
    """Run one record -> transcribe -> respond cycle."""
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

        if TTS_ENABLED:
            print("\nSpeaking response...")
            try:
                speak_text(response)
            except RuntimeError as exc:
                print(f"[WARN] {exc}")
        print()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}\n")
    finally:
        cleanup_temp_file(wav_path)


def main_loop() -> int:
    """Interactive terminal loop."""
    button = None
    try:
        api_key = check_api_key()
        client = create_openai_client(api_key)
        ensure_recorder_available(AUDIO_DEVICE)
        ensure_tts_available()
        if USE_GPIO_BUTTON:
            button = create_gpio_button(BUTTON_GPIO_PIN)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print("Raspberry Pi Voice Input Milestone")
    print("----------------------------------")
    print(f"Recorder: arecord | Duration: {RECORD_SECONDS}s")
    print(f"Sample rate: {SAMPLE_RATE} Hz | Channels: {CHANNELS}")
    print(f"Audio device: {AUDIO_DEVICE or 'default'}")
    print(
        f"TTS: {'enabled' if TTS_ENABLED else 'disabled'} "
        f"({TTS_COMMAND} -> {TTS_OUTPUT_DEVICE})"
    )
    if USE_GPIO_BUTTON:
        print(f"Input mode: GPIO button on BCM pin {BUTTON_GPIO_PIN}")
        print("Press the GPIO button to record. Use Ctrl+C to exit.\n")
    else:
        print("Input mode: keyboard")
        print("Press Enter to record, or type q / quit to exit.\n")

    try:
        while True:
            if USE_GPIO_BUTTON:
                assert button is not None
                button.wait_for_press()
                print("> Button pressed")
                run_interaction_cycle(client)
                button.wait_for_release()
            else:
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
                run_interaction_cycle(client)
    finally:
        if button is not None:
            button.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main_loop())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        raise SystemExit(0)
