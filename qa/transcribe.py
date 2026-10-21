"""Transcription without a Zoom transcript: faster-whisper (CPU, int8) under a time budget.

A 2-minute probe measures speed. If the whole class fits in the budget it is transcribed in full;
otherwise only the opening, the closing and evenly spaced windows are, and the result says so.
Audio is cut with ffmpeg into temp files inside the caller's temp folder; transcript text is never logged.
"""
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

from .config import WHISPER_BUDGET_MIN, WHISPER_MODEL, WHISPER_THREADS
from .ingest import Cue

PROBE_S = 120
CHUNK_S = 300
FIRST_WINDOW_S = 600  # opening kept whole when sampling (rapport, welcomes)
LAST_WINDOW_S = 240  # closing kept (recap, goodbye)
WINDOW_S = 180
MIN_WINDOW_S = 30
PROBE_MIN_SPEECH = 0.4  # a probe with less speech than this (fraction of the window) understates the real speed
OVERRUN = 1.2  # a full run that is projected to exceed the budget by this factor switches to sampling

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=WHISPER_THREADS)
    return _MODEL


def sampled_windows(duration: float, covered_end: float, budget_left_s: float, speed: float) -> list[tuple[float, float]]:
    """Priority-ordered windows: the closing, the rest of the opening, then evenly spaced middle windows that fit the budget."""
    wins = []
    close_start = max(duration - LAST_WINDOW_S, FIRST_WINDOW_S, covered_end)
    if close_start < duration:
        wins.append((close_start, duration))
    if covered_end < min(FIRST_WINDOW_S, duration):
        wins.append((covered_end, min(FIRST_WINDOW_S, duration)))
    mid_a, mid_b = max(FIRST_WINDOW_S, covered_end), close_start
    spent = sum(e - s for s, e in wins) * speed
    affordable = int(max(0.0, budget_left_s - spent) / (speed * WINDOW_S)) if speed > 0 else 0
    n = min(affordable, int((mid_b - mid_a) // WINDOW_S))
    if n > 0:
        gap = (mid_b - mid_a - n * WINDOW_S) / (n + 1)
        wins += [(mid_a + gap * (i + 1) + WINDOW_S * i, mid_a + gap * (i + 1) + WINDOW_S * (i + 1)) for i in range(n)]
    return wins


def _union_len(intervals) -> float:
    total, end = 0.0, -1.0
    for s, e in sorted(intervals):
        s = max(s, end)
        if e > s:
            total += e - s
            end = e
    return total


def run_plan(duration: float, window_fn, budget_s: float, clock=time.monotonic, progress=None):
    """window_fn(start, end) -> list[Cue] with absolute times. Returns (cues, info)."""
    t0 = clock()
    covered: list[tuple[float, float]] = []
    cues: list[Cue] = []

    def do(s, e):
        a = clock()
        got = window_fn(s, e)
        b = clock()
        covered.append((s, e))
        cues.extend(got)
        return b - a

    def tick(msg):
        if progress:
            progress(min(0.99, (clock() - t0) / max(1.0, budget_s)), msg)

    probe_end = min(PROBE_S, duration)
    speed = do(0, probe_end) / max(probe_end, 1.0)  # compute seconds per second of audio
    if probe_end < duration and sum(c.end - c.start for c in cues) < PROBE_MIN_SPEECH * probe_end:
        # The opening is often silent (tutor waiting for children), so the probe understates the speed:
        # probe one chunk from the middle of the class as well (on the chunk grid, so full mode reuses it).
        s2 = probe_end + max(0, round((duration / 2 - probe_end) / CHUNK_S)) * CHUNK_S
        if s2 < duration:
            e2 = min(s2 + CHUNK_S, duration)
            speed = max(speed, do(s2, e2) / (e2 - s2))
    projection = speed * duration
    mode = "full" if projection <= budget_s else "sampled"
    tick("Measured transcription speed")

    pos = probe_end
    if mode == "full":
        while pos < duration:
            end = min(pos + CHUNK_S, duration)
            if any(s <= pos and end <= e for s, e in covered):  # already done by the second probe
                pos = end
                continue
            speed = 0.5 * speed + 0.5 * do(pos, end) / (end - pos)
            pos = end
            tick("Transcribing the class")
            if pos < duration and (clock() - t0) + (duration - pos) * speed > budget_s * OVERRUN:
                mode = "sampled"  # slower than the probe suggested: keep what we have, sample the rest
                break

    if mode == "sampled":
        for s, e in sampled_windows(duration, pos, budget_s - (clock() - t0), speed):
            if any(s < ce and e > cs for cs, ce in covered):
                continue
            e = min(e, s + (budget_s - (clock() - t0)) / max(speed, 1e-6))  # shorten a window that does not fully fit
            if e - s < MIN_WINDOW_S:
                continue
            do(s, e)
            tick("Transcribing sampled parts of the class")

    cues.sort(key=lambda c: c.start)
    covered_s = _union_len(covered)
    info = {
        "mode": mode,
        "partial": covered_s < duration - 1,
        "covered_pct": round(100 * covered_s / max(duration, 1.0)),
        "windows": sorted((round(s), round(e)) for s, e in covered),
        "speed": round(speed, 3),
        "probe_projection_s": round(projection),
        "elapsed_s": round(clock() - t0),
        "budget_s": round(budget_s),
    }
    return cues, info


def _load_wav(path: str) -> np.ndarray:
    """16 kHz mono 16-bit wav -> float32 array. Passing an array avoids faster-whisper's own (PyAV) decoding."""
    with wave.open(path, "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def _extract(media: str, out: str, start: float, length: float):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(length), "-i", media, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out],
        check=True, capture_output=True, timeout=900,
    )


def transcribe_media(media_path: str, duration: float, workdir: str, budget_min: float = WHISPER_BUDGET_MIN, progress=None):
    """Returns (cues, info). Cues have speaker None (no diarization)."""
    model = _model()
    lang = {"v": None}
    wav = str(Path(workdir) / "chunk.wav")

    def window_fn(start, end):
        _extract(media_path, wav, start, end - start)
        segments, info = model.transcribe(
            _load_wav(wav), language=lang["v"], vad_filter=True, beam_size=1, condition_on_previous_text=False
        )
        lang["v"] = lang["v"] or info.language
        return [Cue(start + s.start, start + s.end, None, s.text.strip()) for s in segments if s.text.strip()]

    cues, info = run_plan(duration, window_fn, budget_min * 60, progress=progress)
    info["language"] = lang["v"]
    info["model"] = WHISPER_MODEL
    return cues, info
