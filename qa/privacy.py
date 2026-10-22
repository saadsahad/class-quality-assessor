"""Mask personal first names before anything is displayed or saved.

Three layers, each catching what the one before it misses, since any single source can be fooled.
Over-masking is accepted; a leaked name is not.

1. Exact match on known names: tokens of the Zoom device labels (often "<child>'s iPad") and every
   name/spelling the judge reports. Whole-word, case-insensitive.
2. Fuzzy match: Zoom's own transcription often misspells a name differently in different places
   (e.g. "Riya", "Ria", "Reeya"). Any word of 4+ letters that fuzzy-matches a known name closely
   enough is masked too, tagged under that same known name so repeated misspellings share one tag.
3. Direct-address heuristic: a capitalised word right after "hi", "hey", "say hi to", "very good,"
   or a comma, and right before a sentence-ending comma, period or question mark, is masked even if
   it never matched the known-names list at all - catching a name the judge missed entirely.

ALLOWLIST is a small, curated set of chess and class vocabulary that none of the three layers ever
mask, even when it would otherwise match - it is deliberately short, not a dictionary, because a
common word can also be a real name.
"""
import re

from rapidfuzz import fuzz

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

FUZZY_MIN_LEN = 4
FUZZY_RATIO = 80

_WORD = re.compile(r"[A-Za-z']+")
# Lead-in, a capitalised word, then a lookahead for the closing punctuation (not consumed, so later
# matches in the same sentence - e.g. "Hi Dhruv, how is Meera?" - both still match).
_DIRECT = re.compile(
    r"(?:(?i:hi)\b\s+|(?i:hey)\b\s+|(?i:say hi to)\b\s+|(?i:very good)\s*,\s*|,\s*)"
    r"([A-Z][a-zA-Z'-]{1,})(?=\s*[?.,])"
)


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

    def _fuzzy_match(self, word: str) -> str | None:
        """Best known name this word could be a misspelling of, or None."""
        wl = word.lower()
        if len(wl) < FUZZY_MIN_LEN or wl in ALLOWLIST or not self.names:
            return None
        best_ratio, best_name = 0, None
        for n in self.names:
            r = fuzz.ratio(wl, n)
            if r > best_ratio:
                best_ratio, best_name = r, n
        return best_name if best_ratio >= FUZZY_RATIO else None

    def _fuzzy_pass(self, s: str) -> str:
        def sub(m):
            match = self._fuzzy_match(m.group(0))
            return self._tag(match) if match else m.group(0)

        return _WORD.sub(sub, s)

    def _direct_pass(self, s: str) -> str:
        def sub(m):
            w = m.group(1)
            if w.lower() in ALLOWLIST:
                return m.group(0)
            matched = (w.lower() if w.lower() in self.names else None) or self._fuzzy_match(w) or w.lower()
            return m.group(0)[: -len(w)] + self._tag(matched)

        return _DIRECT.sub(sub, s)

    def text(self, s: str) -> str:
        out = self._rx.sub(lambda m: self._tag(m.group(1)), s) if self._rx else s
        out = self._fuzzy_pass(out)
        out = self._direct_pass(out)
        return out

    def obj(self, o):
        if isinstance(o, str):
            return self.text(o)
        if isinstance(o, dict):
            return {k: self.obj(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [self.obj(v) for v in o]
        return o
