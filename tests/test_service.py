import glob
import os
import tempfile

from qa import service
from qa.media import save_upload, temp_workdir

VTT = b"WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\nTutor: Hello everyone welcome\n"


def _leftovers():
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "qa_*")))


def test_temp_dir_removed_even_on_error():
    before = _leftovers()
    try:
        with temp_workdir() as d:
            path = save_upload(d, "Some Child Name.mp4", b"data")
            assert os.path.basename(path) == "upload.mp4"  # original filename never touches disk
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert _leftovers() == before


def test_service_rejects_non_vtt_and_cleans_up(monkeypatch):
    import pytest

    before = _leftovers()
    with pytest.raises(ValueError):
        service.assess_upload(b"not a transcript", b"\x00\x01", "x.mp4")
    assert _leftovers() == before


def test_service_passes_media_duration(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "probe_duration", lambda p: 1234.0)
    monkeypatch.setattr(service, "assess_cues", lambda cues, **kw: seen.update(kw) or {"ok": True})
    assert service.assess_upload(VTT, b"x", "a.m4a", 3) == {"ok": True}
    assert seen == {"n_students": 3, "media_duration_s": 1234.0}


def test_media_only_transcribes_then_assesses_and_cleans_up(monkeypatch):
    from qa.ingest import Cue

    before = _leftovers()
    seen = {}

    def fake_transcribe(path, duration, workdir, progress=None):
        assert os.path.exists(path) and os.path.basename(path).startswith("upload")
        seen["duration"] = duration
        return [Cue(1, 3, None, "hello class")], {"mode": "sampled", "partial": True, "covered_pct": 55, "budget_s": 600}

    monkeypatch.setattr(service, "probe_duration", lambda p: 2700.0)
    monkeypatch.setattr(service, "transcribe_media", fake_transcribe)
    monkeypatch.setattr(service, "assess_cues", lambda cues, **kw: seen.update(kw) or {"ok": True})
    assert service.assess_upload(None, b"media", "Child Name.mp4", 2) == {"ok": True}
    assert seen["transcript_info"]["covered_pct"] == 55 and seen["media_duration_s"] == 2700.0 and seen["duration"] == 2700.0
    assert _leftovers() == before


def test_no_input_or_unreadable_media():
    import pytest

    with pytest.raises(ValueError):
        service.assess_upload(None, None)
    with pytest.raises(ValueError):
        service.assess_upload(None, b"not media", "x.mp4")  # ffprobe cannot read it
