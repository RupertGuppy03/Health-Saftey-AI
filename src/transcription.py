"""Turn a recorded question into text.

The backend's side of voice input (Sprint 3, story 13). It only transcribes: the
transcript goes back to the interface, where the user checks it and sends it as an
ordinary question. There is no separate answer path for voice.
"""

from pathlib import PurePath

from src.config import settings
from src.config.prompts import TRANSCRIPTION_PROMPT

# The formats browsers record in (webm/ogg from Chrome and Firefox, mp4 from
# Safari), plus the common file types, all of which the transcription API accepts.
AUDIO_EXTENSIONS = {"webm", "ogg", "mp4", "m4a", "wav", "mp3"}


def transcribe(audio_bytes, filename, client):
    """Return {"text", "status"}: "ok" with the transcript, or "empty" if nothing was said.

    Raises ValueError for a recording that cannot be sent: no audio at all, or a
    file type the API does not take. The API reads the format from the filename,
    which is why the extension is checked here.
    """

    if not audio_bytes:
        raise ValueError("The recording is empty.")

    extension = PurePath(filename or "").suffix.lstrip(".").lower()

    if extension not in AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported audio format: {extension or 'none'}.")

    result = client.audio.transcriptions.create(
        model=settings.TRANSCRIPTION_MODEL,
        file=(filename, audio_bytes),
        language=settings.TRANSCRIPTION_LANGUAGE,
        chunking_strategy=settings.TRANSCRIPTION_CHUNKING_STRATEGY,
        prompt=TRANSCRIPTION_PROMPT,
    )

    text = (getattr(result, "text", "") or "").strip()

    return {"text": text, "status": "ok" if text else "empty"}
