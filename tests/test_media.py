import io
import os

import httpx
import pytest

from qa import media


def resolver_for(ip):
    return lambda host, port: [(2, 1, 6, "", (ip, 0))]


def transport(handler):
    return httpx.MockTransport(handler)


def test_direct_link_downloads_and_reports_progress(tmp_path):
    seen = []
    t = transport(lambda req: httpx.Response(200, content=b"x" * 5000, headers={"content-type": "video/mp4", "content-length": "5000"}))
    path = media.download_link(str(tmp_path), "https://files.example.com/class.mp4", progress=lambda f, m: seen.append(f), transport=t, resolver=resolver_for("93.184.216.34"))
    assert os.path.getsize(path) == 5000 and seen and seen[-1] == 1.0


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.9", "169.254.169.254", "::1"])
def test_private_addresses_refused(tmp_path, ip):
    t = transport(lambda req: httpx.Response(200, content=b"secret"))
    with pytest.raises(ValueError, match="public web address"):
        media.download_link(str(tmp_path), "http://internal.example.com/x", transport=t, resolver=resolver_for(ip))


def test_non_http_schemes_refused(tmp_path):
    for url in ("file:///etc/passwd", "ftp://example.com/a", "javascript:alert(1)", "not a url"):
        with pytest.raises(ValueError):
            media.download_link(str(tmp_path), url)


def test_redirect_to_private_address_refused_but_public_redirect_followed(tmp_path):
    hosts = {"a.example.com": "93.184.216.34", "evil.example.com": "10.1.2.3", "b.example.com": "93.184.216.35"}
    resolver = lambda host, port: [(2, 1, 6, "", (hosts[host], 0))]

    def handler(req):
        if req.url.host == "a.example.com":
            return httpx.Response(302, headers={"location": "http://evil.example.com/x"})
        if req.url.host == "b.example.com":
            return httpx.Response(200, content=b"ok" * 10, headers={"content-type": "audio/mp4"})
        return httpx.Response(302, headers={"location": "http://b.example.com/f"})

    with pytest.raises(ValueError, match="public web address"):
        media.download_link(str(tmp_path), "http://a.example.com/x", transport=transport(handler), resolver=resolver)

    hosts["evil.example.com"] = "93.184.216.36"  # same redirect chain, now all public
    path = media.download_link(str(tmp_path), "http://a.example.com/x", transport=transport(handler), resolver=resolver)
    assert os.path.getsize(path) == 20


def test_html_pages_and_oversized_files_refused(tmp_path):
    html = transport(lambda req: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html; charset=utf-8"}))
    with pytest.raises(ValueError, match="web page"):
        media.download_link(str(tmp_path), "https://x.example.com/", transport=html, resolver=resolver_for("93.184.216.34"))
    big = transport(lambda req: httpx.Response(200, content=b"y" * 3000, headers={"content-type": "video/mp4"}))  # no content-length
    with pytest.raises(ValueError, match="larger than"):
        media.download_link(str(tmp_path), "https://x.example.com/a", max_bytes=1000, transport=big, resolver=resolver_for("93.184.216.34"))


def test_drive_links_use_gdown_and_hide_error_details(tmp_path, monkeypatch):
    fid = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
    assert media.drive_file_id(f"https://drive.google.com/file/d/{fid}/view?usp=sharing") == fid
    assert media.drive_file_id(f"https://drive.google.com/open?id={fid}") == fid
    assert media.drive_file_id("https://example.com/a.mp4") is None

    calls = {}

    def fake_gdown(file_id, path, progress=None):
        calls["id"] = file_id
        open(path, "wb").write(b"abc")

    monkeypatch.setattr(media, "gdown_download", fake_gdown)
    p = media.download_link(str(tmp_path), f"https://drive.google.com/file/d/{fid}/view")
    assert calls["id"] == fid and os.path.getsize(p) == 3

    def failing(file_id, path, progress=None):
        raise RuntimeError("internal detail with a private-looking token")

    monkeypatch.setattr(media, "gdown_download", failing)
    with pytest.raises(ValueError) as e:
        media.download_link(str(tmp_path), f"https://drive.google.com/file/d/{fid}/view")
    assert "Anyone with the link" in str(e.value) and "token" not in str(e.value)


def test_stage_media_streams_file_like_with_neutral_name(tmp_path):
    p = media.stage_media(str(tmp_path), io.BytesIO(b"data"), "Child Name.MP4")
    assert os.path.basename(p) == "upload.mp4" and open(p, "rb").read() == b"data"
    p2 = media.stage_media(str(tmp_path), b"bytes", "x.m4a")
    assert os.path.basename(p2) == "upload.m4a"
