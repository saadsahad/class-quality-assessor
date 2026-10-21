"""Pre-push safety check for the public GitHub repo (the app is deployed from it on Streamlit Community Cloud).

    python check_push.py          scan the files git tracks or has staged (or, before `git init`, the files that would be added)
    python check_push.py --tree   scan the files that would be added, ignoring git

Refuses (exit 1) if any scanned file is .env / secrets.toml, a recording / transcript / archive, inside calib_out/,
or contains an API-key pattern. Also checks the deploy settings the app relies on. It never uploads or pushes anything.
"""
import argparse
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# What the repo is meant to contain (used before `git init`, or with --tree).
INTENDED_FILES = [
    "README.md", "app.py", "calibrate.py", "check_push.py", "requirements.txt", "packages.txt",
    ".gitignore", ".streamlit/config.toml",
]
INTENDED_GLOBS = ["qa/*.py", "tests/*.py"]

FORBIDDEN_NAMES = {".env", "secrets.toml"}
FORBIDDEN_EXT = {".mp4", ".m4a", ".vtt", ".zip", ".mov", ".mkv", ".webm", ".mp3", ".wav"}
FORBIDDEN_DIRS = {"calib_out"}
# patterns are assembled so this file does not match its own scan
SECRET_PATTERNS = {
    "Anthropic key": re.compile("sk-" + "ant" + r"[\w-]*"),
    "Google key": re.compile("AI" + "za" + r"[\w-]{10,}"),
    "Hugging Face token": re.compile("hf_" + r"[A-Za-z0-9]{30,}"),
    "generic sk- key": re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
}
REQUIRED_PACKAGES = ["streamlit", "anthropic", "pydantic", "rapidfuzz", "faster-whisper", "gdown", "httpx"]
GITIGNORE_MUST_HAVE = [".env", "calib_out/", "*.vtt", "*.mp4", "*.zip", ".streamlit/secrets.toml"]


def intended_files() -> list[Path]:
    files = [ROOT / f for f in INTENDED_FILES]
    for g in INTENDED_GLOBS:
        files += sorted(ROOT.glob(g))
    return files


def git_files() -> list[Path] | None:
    """Tracked plus staged files, or None if this is not a git repository."""
    out = set()
    for cmd in (["git", "ls-files"], ["git", "diff", "--cached", "--name-only"]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            return None
        out |= {ROOT / line for line in r.stdout.splitlines() if line}
    return sorted(out)


def forbidden(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        rel = f.relative_to(ROOT)
        if f.name in FORBIDDEN_NAMES or f.suffix.lower() in FORBIDDEN_EXT or FORBIDDEN_DIRS & set(rel.parts):
            problems.append(f"forbidden file: {rel}")
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, rx in SECRET_PATTERNS.items():
            if rx.search(text):
                problems.append(f"{name} pattern found in {rel}")
    return problems


def settings_checks() -> list[tuple[bool, str]]:
    res = []

    def ok(cond, msg):
        res.append((bool(cond), msg))

    pk = ROOT / "packages.txt"
    ok(pk.is_file() and "ffmpeg" in pk.read_text().split(), "packages.txt lists ffmpeg")

    cfg_path = ROOT / ".streamlit/config.toml"
    ok(cfg_path.is_file(), ".streamlit/config.toml present")
    if cfg_path.is_file():
        server = tomllib.loads(cfg_path.read_text()).get("server", {})
        ok(isinstance(server.get("maxUploadSize"), int) and server["maxUploadSize"] >= 500, f"config.toml: maxUploadSize = {server.get('maxUploadSize')} MB (>= 500)")
        ok(server.get("enableXsrfProtection") is False, f"config.toml: enableXsrfProtection = {server.get('enableXsrfProtection')} (agreed: false)")
        ok("port" not in server, "config.toml does not override the server port")

    req = ROOT / "requirements.txt"
    reqs = req.read_text().lower() if req.is_file() else ""
    for pkg in REQUIRED_PACKAGES:
        ok(re.search(rf"^{pkg}\b", reqs, re.M), f"requirements.txt: {pkg}")

    readme = (ROOT / "README.md").read_text().lower() if (ROOT / "README.md").is_file() else ""
    ok("streamlit community cloud" in readme, "README mentions Streamlit Community Cloud")
    ok("xsrf" in readme, "README mentions the XSRF setting")
    ok(not readme.startswith("---"), "README has no Hugging Face Space header")

    gi = (ROOT / ".gitignore").read_text().split() if (ROOT / ".gitignore").is_file() else []
    for pat in GITIGNORE_MUST_HAVE:
        ok(pat in gi, f".gitignore ignores {pat}")

    for f in intended_files():
        if f.suffix == ".py" and f.is_file():
            try:
                ast.parse(f.read_text())
            except SyntaxError as e:
                ok(False, f"syntax error in {f.relative_to(ROOT)}: {e.msg}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", action="store_true", help="scan the files that would be added, ignoring git")
    args = ap.parse_args()

    files = None if args.tree else git_files()
    source = "tracked or staged in git"
    if files is None:
        files, source = intended_files(), "that would be added (not a git repository yet)"
    print(f"Files {source} ({len(files)}):")
    for f in files:
        print(f"  {f.relative_to(ROOT)}")

    print("\nChecks:")
    checks = settings_checks()
    for passed, msg in checks:
        print(f"  [{'ok' if passed else 'FAIL'}] {msg}")
    problems = forbidden(files)
    print(f"  [{'FAIL' if problems else 'ok'}] safety scan (.env, media, .vtt, .zip, calib_out/, key patterns)")
    for p in problems:
        print(f"        {p}")

    failed = [m for ok_, m in checks if not ok_] + problems
    if failed:
        print(f"\nDO NOT PUSH: {len(failed)} problem(s) above.")
        sys.exit(1)
    print("\nOK to push. Nothing was pushed by this script.")


if __name__ == "__main__":
    main()
