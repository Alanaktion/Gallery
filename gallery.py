#!/usr/bin/env python3
"""Lightweight image gallery server."""

import argparse
import json
import mimetypes
import re
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif',
              '.webp', '.bmp', '.tiff', '.tif', '.avif'}
VIDEO_EXTS = {'.mp4', '.webm', '.ogv', '.ogg', '.mov', '.m4v', '.mkv', '.avi'}
ALL_MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

ROOT: Path = Path('.')  # resolved absolute path, set in main()
STATIC_DIR: Path = Path(__file__).parent / 'static'


def natural_key(s: str) -> list:
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def media_type(name: str) -> str:
    return 'video' if Path(name).suffix.lower() in VIDEO_EXTS else 'image'


def validate_rel_path(s: str) -> bool:
    """Return True if s is a safe relative path (no traversal, no backslash)."""
    if not isinstance(s, str):
        return False
    if s == '':
        return True
    if '\\' in s:
        return False
    for part in s.split('/'):
        if part in ('', '.', '..'):
            return False
    return True


def resolve_safe(rel: str) -> Path | None:
    """Resolve rel within ROOT. Returns absolute Path or None if unsafe."""
    try:
        p = (ROOT / rel).resolve()
        p.relative_to(ROOT)  # raises ValueError if outside ROOT
        return p
    except (ValueError, OSError):
        return None


def unique_dest(dest_dir: Path, name: str) -> Path:
    """Return a unique path in dest_dir for name, adding _1, _2, … suffixes."""
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while True:
        dest = dest_dir / f'{stem}_{i}{suffix}'
        if not dest.exists():
            return dest
        i += 1


def safe_dest_dir(parent: Path, name: str) -> Path | None:
    """
    Return an existing-or-creatable directory at parent/name.
    Returns None if a non-directory or symlink already exists there.
    """
    d = parent / name
    if d.is_symlink():
        return None
    if d.exists() and not d.is_dir():
        return None
    d.mkdir(exist_ok=True)
    try:
        d.resolve().relative_to(ROOT)
    except ValueError:
        return None
    return d



# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default access log

    def send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def err_json(self, msg: str, status: int = 400) -> None:
        self.send_json({'error': msg}, status)

    def read_json_body(self) -> dict | None:
        length = int(self.headers.get('Content-Length', 0))
        if not length:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        p = parsed.path
        qs = parse_qs(parsed.query)

        if p in ('/', '/index.html'):
            self._serve_html()
        elif p.startswith('/static/'):
            self._serve_static(p[len('/static/'):])
        elif p.startswith('/files/'):
            self._serve_media(unquote(p[len('/files/'):]))
        elif p == '/api/list':
            self._api_list(qs.get('path', [''])[0])
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        p = urlparse(self.path).path
        body = self.read_json_body()
        if not isinstance(body, dict) or 'path' not in body:
            self.err_json('missing path')
            return
        if p == '/api/favorite':
            self._api_move(body['path'], 'fav')
        elif p == '/api/delete':
            self._api_move(body['path'], 'trash')
        elif p == '/api/empty-trash':
            self._api_empty_trash(body['path'])
        elif p == '/api/empty-nonfavs':
            self._api_empty_nonfavs(body['path'])
        elif p == '/api/delete-dir':
            self._api_delete_dir(body['path'])
        else:
            self.send_error(404)

    # ── Route implementations ───────────────────────────────────

    def _serve_html(self) -> None:
        try:
            body = (STATIC_DIR / 'gallery.html').read_bytes()
        except OSError:
            self.send_error(500, 'gallery.html not found')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, name: str) -> None:
        allowed = {'gallery.css': 'text/css', 'gallery.js': 'text/javascript'}
        if name not in allowed:
            self.send_error(404)
            return
        try:
            body = (STATIC_DIR / name).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', allowed[name])
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_media(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.send_error(400)
            return

        abs_path = resolve_safe(rel)
        if abs_path is None or abs_path.is_symlink() or not abs_path.is_file():
            self.send_error(404)
            return

        if abs_path.suffix.lower() not in ALL_MEDIA_EXTS:
            self.send_error(403)
            return

        mime = mimetypes.guess_type(abs_path.name)[
            0] or 'application/octet-stream'
        size = abs_path.stat().st_size
        range_header = self.headers.get('Range', '').strip()

        if range_header.startswith('bytes='):
            self._serve_range(abs_path, mime, size, range_header[6:])
        else:
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                with open(abs_path, 'rb') as f:
                    shutil.copyfileobj(f, self.wfile)
            except OSError:
                pass

    def _serve_range(self, path: Path, mime: str, size: int, spec: str) -> None:
        m = re.match(r'^(\d*)-(\d*)$', spec)
        if not m:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return

        s_str, e_str = m.group(1), m.group(2)
        if s_str:
            start = int(s_str)
            end = int(e_str) if e_str else size - 1
        else:
            if not e_str:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
            start = max(0, size - int(e_str))
            end = size - 1

        if start >= size or start > end:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return

        end = min(end, size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except OSError:
            pass

    def _api_list(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_path = resolve_safe(rel)
        if abs_path is None or abs_path.is_symlink() or not abs_path.is_dir():
            self.err_json('not found', 404)
            return

        try:
            entries = list(abs_path.iterdir())
        except PermissionError:
            self.err_json('permission denied', 403)
            return

        dirs = sorted(
            [e.name for e in entries if e.is_dir() and not e.is_symlink()],
            key=natural_key,
        )
        media = sorted(
            [e.name for e in entries
             if e.is_file() and not e.is_symlink()
             and e.suffix.lower() in ALL_MEDIA_EXTS],
            key=natural_key,
        )
        fav_dirs = [
            d for d in dirs
            if (abs_path / d / 'fav').is_dir() and not (abs_path / d / 'fav').is_symlink()
        ]
        self.send_json({
            'dirs': dirs,
            'fav_dirs': fav_dirs,
            'media': [{'name': n, 'type': media_type(n)} for n in media],
            'has_trash': 'trash' in dirs,
            'has_fav': 'fav' in dirs,
        })

    def _api_move(self, rel: str, dest_name: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_src = resolve_safe(rel)
        if abs_src is None or abs_src.is_symlink() or not abs_src.is_file():
            self.err_json('file not found', 404)
            return

        if abs_src.suffix.lower() not in ALL_MEDIA_EXTS:
            self.err_json('not a supported media file', 400)
            return

        dest_dir = safe_dest_dir(abs_src.parent, dest_name)
        if dest_dir is None:
            self.err_json(f'cannot create {dest_name} directory', 500)
            return

        dest = unique_dest(dest_dir, abs_src.name)
        try:
            shutil.move(str(abs_src), str(dest))
        except OSError as e:
            self.err_json(str(e), 500)
            return

        self.send_json({'ok': True, 'dest': str(dest.relative_to(ROOT))})

    def _api_empty_trash(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_dir = resolve_safe(rel)
        if abs_dir is None or abs_dir.is_symlink() or not abs_dir.is_dir():
            self.err_json('directory not found', 404)
            return

        trash_dir = abs_dir / 'trash'
        if trash_dir.is_symlink() or not trash_dir.is_dir():
            self.err_json('no trash directory', 404)
            return

        deleted = 0
        for entry in list(trash_dir.iterdir()):
            if entry.is_symlink():
                continue
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                deleted += 1
            except OSError:
                pass

        self.send_json({'ok': True, 'deleted': deleted})

    def _api_empty_nonfavs(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_dir = resolve_safe(rel)
        if abs_dir is None or abs_dir.is_symlink() or not abs_dir.is_dir():
            self.err_json('directory not found', 404)
            return

        fav_dir = abs_dir / 'fav'
        if fav_dir.is_symlink() or not fav_dir.is_dir():
            self.err_json('no fav directory', 404)
            return

        deleted = 0
        for entry in list(abs_dir.iterdir()):
            if entry.is_symlink() or entry.is_dir():
                continue
            if entry.suffix.lower() not in ALL_MEDIA_EXTS:
                continue
            try:
                entry.unlink()
                deleted += 1
            except OSError:
                pass

        self.send_json({'ok': True, 'deleted': deleted})

    def _api_delete_dir(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_dir = resolve_safe(rel)
        if abs_dir is None or abs_dir.is_symlink() or not abs_dir.is_dir():
            self.err_json('directory not found', 404)
            return

        # Refuse to delete root or a dir that has trash/fav (use other endpoints instead)
        if abs_dir == ROOT:
            self.err_json('cannot delete root', 400)
            return

        try:
            shutil.rmtree(abs_dir)
        except OSError as e:
            self.err_json(str(e), 500)
            return

        self.send_json({'ok': True})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global ROOT

    parser = argparse.ArgumentParser(
        description='Lightweight image/video gallery server.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n  gallery.py\n  gallery.py ~/Photos\n  gallery.py ~/Photos -p 9000',
    )
    parser.add_argument('root', nargs='?', default='.', metavar='PATH',
                        help='Root media directory (default: current directory)')
    parser.add_argument('-p', '--port', type=int, default=8000, metavar='PORT',
                        help='Port to listen on (default: 8000)')
    parser.add_argument('--host', default='127.0.0.1', metavar='HOST',
                        help='Interface to bind to (default: 127.0.0.1)')
    args = parser.parse_args()

    try:
        ROOT = Path(args.root).resolve(strict=True)
    except FileNotFoundError:
        print(f'Error: path not found: {args.root}', file=sys.stderr)
        sys.exit(1)

    if not ROOT.is_dir():
        print(f'Error: not a directory: {args.root}', file=sys.stderr)
        sys.exit(1)

    if args.host not in ('127.0.0.1', 'localhost', '::1'):
        print(
            f'Warning: binding to {args.host} exposes the gallery '
            f'(and file move/delete) to all reachable hosts.',
            file=sys.stderr,
        )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Serving {ROOT}')
    print(f'Open:   http://{args.host}:{args.port}')
    print('Press Ctrl-C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
