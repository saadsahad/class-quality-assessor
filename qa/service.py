"""Glue between the UI and the pipeline: nothing here is written to disk beyond a temp folder that is always removed."""
from .ingest import parse_vtt
from .media import probe_duration, stage_media, temp_workdir
from .pipeline import assess_cues
from .transcribe import transcribe_media


def assess_upload(
    vtt_bytes: bytes | None,
    media=None,
    media_name: str = "",
    n_students: int | None = None,
    progress=None,
):
    """With a Zoom transcript, use it (a recording only gives the class length; a link is ignored).
    Without one, transcribe the recording. media: bytes, a file-like upload, or a link (str)."""
    if vtt_bytes:
        duration = None
        if media is not None and not isinstance(media, str):
            with temp_workdir() as d:  # media is only needed for its length; the folder is gone before the API call
                duration = probe_duration(stage_media(d, media, media_name))
        cues = parse_vtt(vtt_bytes.decode("utf-8", errors="replace"))
        if not cues:
            raise ValueError("No speech found in that transcript. Please upload the Zoom .vtt file.")
        return assess_cues(cues, n_students=n_students or None, media_duration_s=duration)

    if not media:
        raise ValueError("Please upload a Zoom transcript (.vtt) or a recording.")
    with temp_workdir() as d:
        path = stage_media(d, media, media_name, progress)
        duration = probe_duration(path)
        if not duration:
            raise ValueError("Could not read that recording. Please upload an mp4, m4a, mp3 or wav file.")
        cues, info = transcribe_media(path, duration, d, progress=progress)
    if not cues:
        raise ValueError("No speech was found in that recording.")
    return assess_cues(cues, n_students=n_students or None, media_duration_s=duration, transcript_info=info)
