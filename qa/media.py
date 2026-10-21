"""Uploaded or linked media. Files live only inside a temp folder that is always deleted."""
import contextlib
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urljoin, urlparse

import httpx

MAX_DOWNLOAD_BYTES = 2_000_000_000
MAX_REDIRECTS = 5
CHUNK = 8 * 1024 * 1024


@contextlib.contextmanager
def temp_workdir():
    d = tempfile.mkdtemp(prefix="qa_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def probe_duration(path: str) -> float | None:
    """Media length in seconds via ffprobe, or None if ffprobe is missing or the file is unreadable."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _neutral_path(workdir: str, name: str) -> str:
    """Original file names may contain personal names, so only the extension is kept."""
    return os.path.join(workdir, "upload" + os.path.splitext(name)[1].lower()[:8])


def save_upload(workdir: str, name: str, data: bytes) -> str:
    path = _neutral_path(workdir, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def copy_stream(workdir: str, name: str, fileobj) -> str:
    """Stream a file-like object (e.g. a Streamlit upload) to disk in chunks, without a second in-memory copy."""
    path = _neutral_path(workdir, name)
    with open(path, "wb") as f:
        shutil.copyfileobj(fileobj, f, CHUNK)
    return path


# ---- links -------------------------------------------------------------------------------------

_DRIVE = re.compile(r"(?:drive|docs)\.google\.com/.*?(?:/d/|[?&]id=)([\w-]{20,})")


def drive_file_id(url: str) -> str | None:
    m = _DRIVE.search(url)
    return m.group(1) if m else None


def gdown_download(file_id: str, path: str, progress=None):
    import gdown  # Google Drive's large-file confirmation page needs gdown's handling

    return gdown.download(id=file_id, output=path, quiet=True, progress=progress)


def _is_public(host: str, resolver=socket.getaddrinfo) -> bool:
    """Refuse links that point at this machine or a private network (SSRF protection)."""
    try:
        infos = resolver(host, None)
    except OSError:
        return False
    ips = {ipaddress.ip_address(i[4][0]) for i in infos}
    return bool(ips) and all(ip.is_global and not ip.is_multicast for ip in ips)


def download_link(workdir: str, url: str, progress=None, max_bytes: int = MAX_DOWNLOAD_BYTES, transport=None, resolver=socket.getaddrinfo) -> str:
    """Download a Google Drive share link or a direct http(s) link to a temp file. Raises ValueError with a safe message."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Please paste a full http(s) link.")
    path = os.path.join(workdir, "upload.bin")

    file_id = drive_file_id(url)
    if file_id:
        try:
            gdown_download(file_id, path, progress=(lambda done, total: progress(done / total if total else 0.0, "Downloading the recording")) if progress else None)
        except Exception:
            raise ValueError("Could not download that Google Drive file. Check that sharing is set to 'Anyone with the link'.") from None
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError("Could not download that Google Drive file. Check that sharing is set to 'Anyone with the link'.")
        if os.path.getsize(path) > max_bytes:
            os.remove(path)
            raise ValueError(f"That file is larger than {max_bytes // 1_000_000} MB.")
        return path

    with httpx.Client(transport=transport, timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            host = urlparse(url).hostname
            if not host or not _is_public(host, resolver):
                raise ValueError("That link does not point to a public web address.")
            with client.stream("GET", url) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers.get("location", ""))
                    if urlparse(url).scheme not in ("http", "https"):
                        raise ValueError("That link redirects somewhere that is not http(s).")
                    continue
                if r.status_code != 200:
                    raise ValueError(f"The link could not be downloaded (status {r.status_code}).")
                if "text/html" in r.headers.get("content-type", ""):
                    raise ValueError("That link returns a web page, not a recording. Paste a direct link to the file.")
                total = int(r.headers.get("content-length") or 0)
                if total > max_bytes:
                    raise ValueError(f"That file is larger than {max_bytes // 1_000_000} MB.")
                done = 0
                with open(path, "wb") as f:
                    for chunk in r.iter_bytes(CHUNK):
                        done += len(chunk)
                        if done > max_bytes:
                            raise ValueError(f"That file is larger than {max_bytes // 1_000_000} MB.")
                        f.write(chunk)
                        if progress:
                            progress(done / total if total else 0.0, "Downloading the recording")
                return path
    raise ValueError("Too many redirects.")


def stage_media(workdir: str, media, name: str = "", progress=None) -> str:
    """Put the media in workdir under a neutral name. media: bytes, a file-like object, or a link (str)."""
    if isinstance(media, (bytes, bytearray)):
        return save_upload(workdir, name, bytes(media))
    if isinstance(media, str):
        return download_link(workdir, media, progress)
    return copy_stream(workdir, name or getattr(media, "name", ""), media)
