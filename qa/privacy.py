"""Mask personal first names before anything is displayed or saved.

Names come from two sources: tokens of the Zoom device labels (often "<child>'s iPad") and the
list of names the judge reports. Whole-word, case-insensitive; over-masking is preferred to leaking.
"""
import re

_GENERIC = {
    "iphone", "ipad", "android", "samsung", "galaxy", "zoom", "user", "guest", "laptop", "pc", "mac",
    "macbook", "tablet", "phone", "host", "tutor", "teacher", "student", "parent", "mom", "dad",
    "mobile", "tab", "pad", "the", "and", "of", "my", "room", "class", "chess", "learner",
}


def names_from_labels(labels) -> set[str]:
    out = set()
    for label in labels:
        for tok in re.findall(r"[A-Za-z]+", label or ""):
            if len(tok) >= 3 and tok.lower() not in _GENERIC:
                out.add(tok.lower())
    return out


class Masker:
    def __init__(self, names):
        self.names = sorted({n.strip().lower() for n in names if len(n.strip()) >= 2}, key=len, reverse=True)
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
