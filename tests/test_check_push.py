import importlib.util
import pathlib

SPEC = importlib.util.spec_from_file_location("check_push", pathlib.Path(__file__).resolve().parent.parent / "check_push.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


def _files(tmp_path, monkeypatch, names_and_text):
    monkeypatch.setattr(check, "ROOT", tmp_path)
    out = []
    for name, text in names_and_text.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        out.append(p)
    return out


def test_clean_files_pass(tmp_path, monkeypatch):
    assert check.forbidden(_files(tmp_path, monkeypatch, {"app.py": "print('hi')", "qa/x.py": "x = 1"})) == []


def test_forbidden_names_media_and_dirs_refused(tmp_path, monkeypatch):
    files = _files(tmp_path, monkeypatch, {".env": "A=1", "class.vtt": "WEBVTT", "a.m4a": "x", "b.mp4": "x", "c.zip": "x", "calib_out/results.json": "{}", ".streamlit/secrets.toml": "k='v'"})
    assert len(check.forbidden(files)) == 7


def test_key_patterns_refused(tmp_path, monkeypatch):
    anthropic_key = "sk-" + "ant-api03-" + "abcdef123456"
    google_key = "AI" + "zaSyD-abcdefghijklmnop"
    problems = check.forbidden(_files(tmp_path, monkeypatch, {"a.py": f'KEY = "{anthropic_key}"', "b.py": f'K = "{google_key}"'}))
    assert any("Anthropic" in p for p in problems) and any("Google" in p for p in problems)


def test_real_repo_settings_and_files_are_clean():
    failed = [m for ok, m in check.settings_checks() if not ok]
    assert failed == [] and check.forbidden(check.intended_files()) == []
