import tempfile
import os
from faster_whisper import WhisperModel
from config.settings import settings

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type="int8",
        )
    return _model


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> dict:
    """Transcribe audio bytes. Returns {"text": str, "language": str}."""
    suffix = os.path.splitext(filename)[1] or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = get_model()
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join([seg.text.strip() for seg in segments]).strip()
        return {"text": text, "language": info.language}
    finally:
        os.unlink(tmp_path)
