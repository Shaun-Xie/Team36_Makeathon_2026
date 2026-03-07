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
ELEVENLABS_MODEL_ID = "eleven_turbo_v2_5"
ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
ELEVENLABS_OUTPUT_FORMAT = "pcm_16000"
ELEVENLABS_SAMPLE_RATE = 16000
ELEVENLABS_CHANNELS = 1
TTS_OUTPUT_DEVICE = os.getenv("TTS_OUTPUT_DEVICE", "default")
# Example Bluetooth ALSA device: bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp

SYSTEM_PROMPT = (
    "You are a friendly interactive zoo guide speaking with visitors in real time. "
    "Give short, clear, natural spoken answers that are easy to understand in a live conversation. "
    "Keep most responses to 1 or 2 sentences, usually under 45 words, unless the visitor asks for more detail. "
    "Answer the question directly first, then add at most one interesting educational detail. "
    "Focus on animals, habitats, ecology, conservation, biodiversity, pollution, climate change, "
    "and how humans affect ecosystems. "
    "Avoid long lists, long descriptions, repeated details, and overly technical language. "
    "Sound warm, engaging, and informative, like a real zoo guide talking to the public."
)


def check_api_key() -> str:
    """Return OPENAI_API_KEY or raise a clear error."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Missing OPENAI_API_KEY. Export it in your shell before running."
        )
    return api_key


def check_elevenlabs_api_key() -> str:
    """Return ELEVENLABS_API_KEY or raise a clear error."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Missing ELEVENLABS_API_KEY. Export it in your shell before running."
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


def create_elevenlabs_client(api_key: str):
    """Create ElevenLabs SDK client."""
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as exc:
        raise RuntimeError(
            "ElevenLabs package is not installed. Run: pip install -r requirements.txt"
        ) from exc

    return ElevenLabs(api_key=api_key)


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
    """Verify local playback path and output device when TTS is enabled."""
    if not TTS_ENABLED:
        return

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


def synthesize_speech(client, text: str) -> str:
    """Generate ElevenLabs PCM audio from text and return temp file path."""
    if not text.strip():
        raise RuntimeError("Cannot synthesize empty text.")

    temp_pcm = tempfile.NamedTemporaryFile(
        prefix="elevenlabs_tts_", suffix=".pcm", delete=False
    )
    temp_pcm_path = temp_pcm.name
    temp_pcm.close()

    try:
        audio_stream = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            model_id=ELEVENLABS_MODEL_ID,
            output_format=ELEVENLABS_OUTPUT_FORMAT,
            text=text,
        )
    except Exception as exc:
        cleanup_temp_file(temp_pcm_path)
        raise RuntimeError(f"ElevenLabs request failed: {exc}") from exc

    bytes_written = 0
    try:
        with open(temp_pcm_path, "wb") as audio_file:
            if isinstance(audio_stream, (bytes, bytearray)):
                audio_file.write(audio_stream)
                bytes_written += len(audio_stream)
            else:
                for chunk in audio_stream:
                    if isinstance(chunk, (bytes, bytearray)) and chunk:
                        audio_file.write(chunk)
                        bytes_written += len(chunk)
    except OSError as exc:
        cleanup_temp_file(temp_pcm_path)
        raise RuntimeError(f"Failed writing ElevenLabs audio file: {exc}") from exc

    if bytes_written == 0:
        cleanup_temp_file(temp_pcm_path)
        raise RuntimeError("ElevenLabs returned empty audio.")

    return temp_pcm_path


def play_audio_file(path: str) -> None:
    """Play a PCM audio file with ALSA on Raspberry Pi/Linux."""
    audio_path = Path(path)
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Playback failed: audio file is missing or empty.")

    cmd = [
        "aplay",
        "-q",
        "-f",
        "S16_LE",
        "-r",
        str(ELEVENLABS_SAMPLE_RATE),
        "-c",
        str(ELEVENLABS_CHANNELS),
    ]
    if TTS_OUTPUT_DEVICE and TTS_OUTPUT_DEVICE != "default":
        cmd.extend(["-D", TTS_OUTPUT_DEVICE])
    cmd.append(path)

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown playback error"
        raise RuntimeError(f"Playback failed.\naplay error: {stderr}")


def speak_text(client, text: str) -> None:
    """Synthesize and play assistant speech using ElevenLabs."""
    if not TTS_ENABLED:
        return

    temp_pcm_path = None
    try:
        temp_pcm_path = synthesize_speech(client, text)
        play_audio_file(temp_pcm_path)
    finally:
        cleanup_temp_file(temp_pcm_path)


def cleanup_temp_file(path: Optional[str]) -> None:
    """Best-effort temp file cleanup."""
    if not path:
        return
    try:
        if Path(path).exists():
            os.remove(path)
    except OSError as exc:
        print(f"[WARN] Could not remove temp file {path}: {exc}")


def run_interaction_cycle(openai_client, elevenlabs_client=None) -> None:
    """Run one record -> transcribe -> respond cycle."""
    wav_path = create_temp_wav_path()
    try:
        print(f"Recording {RECORD_SECONDS} seconds...")
        record_audio(wav_path, seconds=RECORD_SECONDS)

        print("Transcribing with OpenAI...")
        transcript = transcribe_audio(openai_client, wav_path)
        print("\nTranscript:")
        print(transcript)

        print("\nGenerating assistant response...")
        response = get_assistant_response(openai_client, transcript)
        print("\nAssistant response:")
        print(response)

        if TTS_ENABLED and elevenlabs_client is not None:
            print("\nSpeaking response with ElevenLabs...")
            try:
                speak_text(elevenlabs_client, response)
            except RuntimeError as exc:
                print(f"[WARN] {exc}")
        elif TTS_ENABLED:
            print("\n[WARN] TTS is enabled but ElevenLabs is not configured.")

        print()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}\n")
    finally:
        cleanup_temp_file(wav_path)


def main_loop() -> int:
    """Interactive terminal loop."""
    button = None
    elevenlabs_client = None
    tts_ready = False

    try:
        openai_api_key = check_api_key()
        openai_client = create_openai_client(openai_api_key)
        ensure_recorder_available(AUDIO_DEVICE)

        if USE_GPIO_BUTTON:
            button = create_gpio_button(BUTTON_GPIO_PIN)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    if TTS_ENABLED:
        try:
            elevenlabs_api_key = check_elevenlabs_api_key()
            elevenlabs_client = create_elevenlabs_client(elevenlabs_api_key)
            ensure_tts_available()
            tts_ready = True
        except RuntimeError as exc:
            print(f"[WARN] ElevenLabs TTS disabled: {exc}")

    print("Raspberry Pi Voice Input Milestone")
    print("----------------------------------")
    print(f"Recorder: arecord | Duration: {RECORD_SECONDS}s")
    print(f"Sample rate: {SAMPLE_RATE} Hz | Channels: {CHANNELS}")
    print(f"Audio device: {AUDIO_DEVICE or 'default'}")
    print(
        f"TTS: {'enabled' if tts_ready else 'disabled'} "
        f"(ElevenLabs voice={ELEVENLABS_VOICE_ID}, model={ELEVENLABS_MODEL_ID}, "
        f"output={TTS_OUTPUT_DEVICE})"
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
                run_interaction_cycle(openai_client, elevenlabs_client)
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

                run_interaction_cycle(openai_client, elevenlabs_client)
    finally:
        if button is not None:
            button.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main_loop())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        raise SystemExit(0)
