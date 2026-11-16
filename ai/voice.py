"""
voice.py
========
Purpose : Speech in and speech out for the assistant.
Location: ai/voice.py
Used by : views/assistant.py

Speech out : the Mac's built-in `say` command. Nothing to install.
Speech in  : a local Whisper model if one is installed (audio never leaves your Mac).
             Tried in this order: mlx-whisper, faster-whisper, openai-whisper.
             With none installed, use macOS dictation in the chat box instead
             (System Settings > Keyboard > Dictation, then press the microphone key).
"""

import platform
import re
import subprocess
import tempfile

import config

_speaker = None          # the running `say` process, so it can be stopped
_whisper_model = None    # loaded once, reused


def can_speak():
    return platform.system() == "Darwin"


def stop_speaking():
    global _speaker
    if _speaker and _speaker.poll() is None:
        _speaker.terminate()
    _speaker = None


def plain_text(markdown):
    """Strip markdown so the voice does not read out symbols."""
    text = re.sub(r"```.*?```", " code block. ", markdown, flags=re.S)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[#*_`>\[\]]", "", text)
    text = re.sub(r"\(https?://\S+\)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def speak(markdown, limit=1800):
    """Read text aloud without blocking the app. Returns False if speech is unavailable."""
    global _speaker
    if not can_speak():
        return False
    stop_speaking()
    try:
        _speaker = subprocess.Popen(["say", "-r", "195", plain_text(markdown)[:limit]])
    except OSError:
        return False
    return True


def stt_engine():
    """Name of the installed speech-to-text package, or None."""
    for module in ("mlx_whisper", "faster_whisper", "whisper"):
        try:
            __import__(module)
            return module
        except ImportError:
            continue
    return None


def transcribe(audio_bytes):
    """Turn recorded audio (WAV bytes) into text. Returns (text, error)."""
    global _whisper_model
    engine = stt_engine()
    if engine is None:
        return None, "No speech-to-text package is installed. See the setup guide, or use macOS dictation."
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        handle.write(audio_bytes)
        path = handle.name
    try:
        if engine == "mlx_whisper":
            import mlx_whisper
            text = mlx_whisper.transcribe(path).get("text", "")
        elif engine == "faster_whisper":
            from faster_whisper import WhisperModel
            if _whisper_model is None:
                _whisper_model = WhisperModel(config.WHISPER_MODEL, compute_type="int8")
            segments, _info = _whisper_model.transcribe(path)
            text = " ".join(segment.text for segment in segments)
        else:
            import whisper
            if _whisper_model is None:
                _whisper_model = whisper.load_model(config.WHISPER_MODEL)
            text = _whisper_model.transcribe(path).get("text", "")
    except Exception as error:
        return None, f"Transcription failed ({engine}): {str(error)[:200]}"
    return text.strip(), None
