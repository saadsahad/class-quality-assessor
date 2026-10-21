from qa.ingest import Cue
from qa.transcribe import run_plan


class Fake:
    """Fake clock + window function: transcribing s..e costs speed(t) * (e - s) seconds."""

    def __init__(self, speed, speech_in_opening=True):
        self.t, self.speed, self.calls = 0.0, speed, []
        self.speech_in_opening = speech_in_opening

    def clock(self):
        return self.t

    def window(self, s, e):
        self.t += (self.speed(s) if callable(self.speed) else self.speed) * (e - s)
        self.calls.append((s, e))
        return [Cue(s, e, None, f"text {s}")] if (s >= 120 or self.speech_in_opening) else []


def test_fast_machine_transcribes_everything():
    f = Fake(0.05)
    cues, info = run_plan(3000, f.window, 600, clock=f.clock)
    assert info["mode"] == "full" and not info["partial"] and info["covered_pct"] == 100
    assert cues[0].start == 0 and cues == sorted(cues, key=lambda c: c.start)


def test_slow_machine_samples_and_stays_in_budget():
    f = Fake(0.5)  # 3000 s of audio would need 1500 s > 600 s budget
    cues, info = run_plan(3000, f.window, 600, clock=f.clock)
    assert info["mode"] == "sampled" and info["partial"] and 0 < info["covered_pct"] < 100
    assert info["elapsed_s"] <= 600
    starts = [s for s, _ in info["windows"]]
    assert starts[0] == 0 and any(e == 3000 for _, e in info["windows"])  # opening and closing both covered
    assert any(s > 700 and e < 2700 for s, e in info["windows"])  # and some middle windows


def test_probe_too_optimistic_switches_to_sampling():
    f = Fake(lambda s: 0.1 if s < 120 else 0.9)  # looks fast for 2 minutes, then slows down
    cues, info = run_plan(3000, f.window, 600, clock=f.clock)
    assert info["mode"] == "sampled" and info["partial"]
    assert info["elapsed_s"] <= 600 * 1.2
    assert any(e == 3000 for _, e in info["windows"])  # closing still captured


def test_short_recording_is_just_the_probe():
    f = Fake(0.1)
    _, info = run_plan(90, f.window, 600, clock=f.clock)
    assert info["covered_pct"] == 100 and info["windows"] == [(0, 90)]


def test_extract_and_load_wav_roundtrip(tmp_path):
    import shutil
    import subprocess

    import numpy as np
    import pytest

    from qa import transcribe

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    src, wav = str(tmp_path / "in.m4a"), str(tmp_path / "out.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:a", "aac", src], check=True)
    transcribe._extract(src, wav, 1, 3)
    audio = transcribe._load_wav(wav)
    assert audio.dtype == np.float32 and abs(len(audio) - 3 * 16000) < 2000 and np.abs(audio).max() > 0.1


def test_silent_opening_does_not_fool_the_probe():
    # first 2 minutes are silent (cheap), the rest is slow: without the second probe this would look fast
    f = Fake(lambda s: 0.01 if s < 120 else 0.5, speech_in_opening=False)
    cues, info = run_plan(3000, f.window, 600, clock=f.clock)
    assert info["mode"] == "sampled" and info["partial"]
    assert info["elapsed_s"] <= 600
    assert len({tuple(w) for w in info["windows"]}) == len(info["windows"])  # no window transcribed twice
    assert any(e == 3000 for _, e in info["windows"])


def test_silent_opening_on_a_fast_machine_still_goes_full_without_duplicates():
    f = Fake(lambda s: 0.01 if s < 120 else 0.05, speech_in_opening=False)
    cues, info = run_plan(3000, f.window, 600, clock=f.clock)
    assert info["mode"] == "full" and info["covered_pct"] == 100
    assert len(f.calls) == len(set(f.calls))  # the middle probe chunk was not repeated


def test_tight_budget_keeps_the_closing_and_shortens_the_opening():
    f = Fake(0.5)
    cues, info = run_plan(3000, f.window, 250, clock=f.clock)  # probe alone costs 60 s; opening+closing would not fit
    assert info["elapsed_s"] <= 250
    assert any(e == 3000 for _, e in info["windows"])  # the closing was kept
    assert all(e - s >= 30 for s, e in info["windows"])
