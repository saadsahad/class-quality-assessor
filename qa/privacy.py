"""Mask personal first names before anything is displayed or saved.

Names come from two sources: tokens of the Zoom device labels (often "<child>'s iPad") and the
list of names the judge reports. Whole-word, case-insensitive; over-masking is preferred to leaking.

The judge's own name list is the weak point: it can include an ordinary word it mistook for a name
(a capitalised word in the transcript, a device label like "Video" or "Screen Share"). ALLOWLIST is a
small, curated set of chess and class vocabulary that is never masked, even if it is reported as a
name. It is deliberately short, not a dictionary: a common word can also be a real name.
"""
import re

_GENERIC = {
    "iphone", "ipad", "android", "samsung", "galaxy", "zoom", "user", "guest", "laptop", "pc", "mac",
    "macbook", "tablet", "phone", "host", "tutor", "teacher", "student", "parent", "mom", "dad",
    "mobile", "tab", "pad", "the", "and", "of", "my", "room", "class", "chess", "learner",
}

ALLOWLIST = {
    "video", "audio", "board", "screen", "camera", "mic", "microphone", "connection", "network", "wifi",
    "internet", "call", "link", "puzzle", "pawn", "rook", "knight", "bishop", "queen", "king",
    "check", "mate", "checkmate", "stalemate", "castle", "castling", "move", "turn", "piece", "square",
    "clock", "timer", "opening", "endgame", "middlegame", "game", "round", "draw", "win", "lose",
    "lesson", "homework", "quiz", "puzzles", "moves", "pieces", "squares",
}


def names_from_labels(labels) -> set[str]:
    out = set()
    for label in labels:
        for tok in re.findall(r"[A-Za-z]+", label or ""):
            if len(tok) >= 3 and tok.lower() not in _GENERIC and tok.lower() not in ALLOWLIST:
                out.add(tok.lower())
    return out


class Masker:
    def __init__(self, names):
        self.names = sorted(
            {n.strip().lower() for n in names if len(n.strip()) >= 2} - ALLOWLIST, key=len, reverse=True
        )
        self._ids: dict[str, str] = {}
        self._rx = (
            re.compile(r"\b(" + "|".join(re.escape(n) for n in self.names) + r")\b", re.I) if self.names else None
        )

    def _tag(self, name: str) -> str:
        key = name.lower()
        if key not in self._ids:
            i = len(self._ids)
            self._ids[key] = f"[Name {chr(65 + i % 26)}{'' if i < 26 else i // 26}]"
        return self._ids[key]

    def text(self, s: str) -> str:
        return self._rx.sub(lambda m: self._tag(m.group(1)), s) if self._rx else s

    def obj(self, o):
        if isinstance(o, str):
            return self.text(o)
        if isinstance(o, dict):
            return {k: self.obj(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [self.obj(v) for v in o]
        return o
