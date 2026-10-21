import pathlib

from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")

FAKE = {
    "rating": {"grade": "Good", "weighted": 2.85, "borderline": ("Average", "Good"), "penalty": 0.0},
    "criteria": {
        "rapport_start": {"score": 3, "judge_score": 3, "rationale": "Greets [Name A].", "evidence": [{"quote": "hello [Name A]", "ts": 65, "speaker": "S1"}], "dropped": 1, "note": "ok", "in_grade": True, "verified_count": 1, "thin_evidence": True},
        "welcome_new": {"score": None, "judge_score": None, "rationale": "none", "evidence": [], "dropped": 0, "note": "ok", "in_grade": True, "verified_count": 0, "thin_evidence": False},
        "warmth_energy": {"score": 2, "judge_score": 4, "rationale": "x", "evidence": [], "dropped": 0, "note": "capped from 4: no verified quote", "in_grade": True, "verified_count": 0, "thin_evidence": True},
        "fair_turns": {"score": 4, "judge_score": 4, "rationale": "x", "evidence": [], "dropped": 0, "note": "ok", "in_grade": False, "verified_count": 0, "thin_evidence": True},
        "lesson_close": {"score": 3, "judge_score": 3, "rationale": "x", "evidence": [], "dropped": 0, "note": "ok", "in_grade": True, "verified_count": 0, "thin_evidence": True},
        "checklist": {"score": 3, "judge_score": 3, "rationale": "x", "evidence": [], "dropped": 0, "note": "ok", "in_grade": True, "verified_count": 0, "thin_evidence": True},
    },
    "signals": {"duration_min": 45},
    "media_segments": [],
    "coverage": {"start": "present", "end": "present", "media_s": 2700},
    "model_cross_check": {"rating": "Good", "reason": "x"},
    "cost_usd": 0.0612,
    "transcript": {"source": "zoom_vtt", "has_speakers": True, "partial": False},
}
ASR = {**FAKE, "signals": {}, "transcript": {"source": "whisper", "has_speakers": False, "partial": True, "covered_pct": 62, "budget_s": 600, "language": "en"}}


def _app(monkeypatch, password="pw"):
    if password:
        monkeypatch.setenv("APP_PASSWORD", password)
    else:
        monkeypatch.delenv("APP_PASSWORD", raising=False)
    return AppTest.from_file(APP, default_timeout=30).run()


def test_not_configured_refuses(monkeypatch):
    at = _app(monkeypatch, password=None)
    assert at.error and "not configured" in at.error[0].value
    assert not at.title and not at.file_uploader


def test_nothing_renders_before_password(monkeypatch):
    at = _app(monkeypatch)
    assert len(at.text_input) == 1 and not at.title and not at.file_uploader and not at.button
    at.text_input[0].set_value("wrong").run()
    assert at.error and "Incorrect" in at.error[0].value and not at.file_uploader


def test_full_flow_shows_band_cost_and_report_only(monkeypatch):
    monkeypatch.setattr("qa.service.assess_upload", lambda *a, **k: FAKE)
    at = _app(monkeypatch)
    at.text_input[0].set_value("pw").run()
    assert at.title and len(at.file_uploader) == 2
    assert at.button[0].disabled  # no transcript yet
    at.file_uploader[0].upload("class.vtt", b"WEBVTT\n").run()
    at.button[0].click().run()
    assert "Good (borderline Average / Good)" in at.subheader[0].value
    labels = [e.label for e in at.expander]
    assert any("Fair turns" in l and "not used in the grade" in l for l in labels)
    assert any("Welcoming new joiners: N/A" in l for l in labels)
    assert "$0.061" in " ".join(c.value for c in at.caption)


def test_cost_guard_message_shown(monkeypatch):
    from qa.judge import CostGuardError

    def refuse(*a, **k):
        raise CostGuardError("Estimated worst-case $0.31 exceeds the $0.20 limit; run refused.")

    monkeypatch.setattr("qa.service.assess_upload", refuse)
    at = _app(monkeypatch)
    at.text_input[0].set_value("pw").run()
    at.file_uploader[0].upload("class.vtt", b"WEBVTT\n").run()
    at.button[0].click().run()
    assert at.error and "run refused" in at.error[0].value


def test_media_only_enables_button_and_shows_partial_banner(monkeypatch):
    monkeypatch.setattr("qa.service.assess_upload", lambda *a, **k: ASR)
    at = _app(monkeypatch)
    at.text_input[0].set_value("pw").run()
    at.file_uploader[1].upload("class.mp4", b"x").run()
    assert not at.button[0].disabled  # a recording alone is enough
    at.button[0].click().run()
    assert any("Partial transcript" in w.value and "62%" in w.value for w in at.warning)
    assert any("Transcribed automatically" in i.value for i in at.info)


def test_password_and_keys_come_from_st_secrets(monkeypatch):
    import os

    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # empty so the app falls back to st.secrets; restored after the test
    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["APP_PASSWORD"] = "from-secrets"
    at.secrets["ANTHROPIC_API_KEY"] = "test-key-value"
    at.run()
    assert at.text_input and not at.error  # gate shown, so the password was found
    at.text_input[0].set_value("from-secrets").run()
    assert at.title
    assert os.environ.get("ANTHROPIC_API_KEY") == "test-key-value"


def test_link_input_enables_button_and_is_passed_as_media(monkeypatch):
    seen = {}

    def capture(vtt, media, name, n, progress=None):
        seen.update(vtt=vtt, media=media)
        return ASR

    monkeypatch.setattr("qa.service.assess_upload", capture)
    at = _app(monkeypatch)
    at.text_input[0].set_value("pw").run()
    assert at.button[0].disabled
    at.text_input[0].set_value("https://drive.google.com/file/d/abc/view").run()  # the link box is the only text input after login
    assert not at.button[0].disabled
    at.button[0].click().run()
    assert seen == {"vtt": None, "media": "https://drive.google.com/file/d/abc/view"}
