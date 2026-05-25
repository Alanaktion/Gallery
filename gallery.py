import argparse
import hashlib
import http.server
import io
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import PIL.Image
import urllib.parse

from contextlib import contextmanager
from html import escape as esc
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from pi_heif import register_heif_opener
    register_heif_opener()
    heif_support = True
except ImportError:
    heif_support = False

ffmpeg = os.environ.get('FFMPEG_PATH', shutil.which('ffmpeg'))
blender = os.environ.get('BLENDER_PATH', shutil.which('blender'))
stl_thumb = os.environ.get('STL_THUMB_PATH', shutil.which('stl-thumb'))
blender_thumb_script = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'blender_thumb.py')


def _check_avif_support():
    try:
        buf = io.BytesIO()
        PIL.Image.new('RGB', (1, 1)).save(buf, 'avif')
        return True
    except Exception:
        return False


avif_support = _check_avif_support()

VIDEO_EXTS = ('.mp4', '.m4v', '.webm')
STL_THUMB_MODEL_EXTS = ('.3mf', '.obj', '.stl')
BLENDER_ONLY_MODEL_EXTS = ('.fbx', '.glb', '.gltf')
BLENDER_MODEL_EXTS = STL_THUMB_MODEL_EXTS + BLENDER_ONLY_MODEL_EXTS
BLENDER_MODEL_EXT_NAMES = tuple(ext.lstrip('.') for ext in BLENDER_MODEL_EXTS)

# Ensure AVIF MIME type is registered for SimpleHTTPRequestHandler to serve correctly
mimetypes.add_type('image/avif', '.avif')


_BOOLEAN_STATES = {'1': True, 'yes': True, 'true': True, 'on': True,
                   '0': False, 'no': False, 'false': False, 'off': False}


def _env_bool(value: str):
    if value.lower() not in _BOOLEAN_STATES:
        return value
    return _BOOLEAN_STATES[value.lower()]


def qe(val: str):
    return esc(urllib.parse.quote(val))


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(',') if part.strip()]


def css():
    styles = """
html, body {
    height: 100%;
    margin: 0;
    padding: 0;
}
body {
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.42857;
    color: #333;
    background-color: #FFF;
}
.container {
    margin: 0 auto;
    padding: 2px 0;
}

.breadcrumbs {
    padding: 0 15px;
    font-size: 16px;
}
.breadcrumbs a {
    color: #428BCA;
    text-decoration: none;
}
.breadcrumbs a:hover,
.breadcrumbs a:focus {
    color: #2A6496;
    text-decoration: underline;
}

a.dir,
a.image,
a.file {
    position: relative;
    display: block;
    width: {SIZE}px;
    height: {SIZE}px;
    object-fit: cover;
    border: 1px solid #fff;
    outline: 1px solid #777;
    margin: 2px;
    float: left;
    text-decoration: none;
}
a.dir:after,
a.image:after,
a.file:after {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    left: 0;
    box-shadow: 1px 1px 0 rgba(255, 255, 255, 0.2) inset,
                -1px -1px 0 rgba(255, 255, 255, 0.2) inset;
}
a.dir {background-color: #eee;}
a.dir:hover, a.dir:focus {background-color: #f5f5f5;}
a.image {background-color: #fff;}
a.file {
    background-color: #444;
    background-image: url('data:image/svg+xml;utf8,%3C%3Fxml%20version%3D%221.0%22%20encoding%3D%22UTF-8%22%20standalone%3D%22no%22%20%3F%3E%3Csvg%20width%3D%2264px%22%20height%3D%2278px%22%20viewBox%3D%220%200%2064%2078%22%20version%3D%221.1%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20xmlns%3Axlink%3D%22http%3A%2F%2Fwww.w3.org%2F1999%2Fxlink%22%3E%3Cg%20stroke%3D%22none%22%20stroke-width%3D%221%22%20fill%3D%22none%22%20fill-rule%3D%22evenodd%22%3E%3Cpath%20d%3D%22M20%2C0%20L0%2C20%20L0%2C78%20L64%2C78%20L64%2C0%20L20%2C0%20Z%22%20fill%3D%22%23D5D5D5%22%3E%3C%2Fpath%3E%3Cpath%20d%3D%22M0.166992188%2C20.0644531%20L20%2C20.0644531%20L20%2C0%20L0.166992188%2C20.0644531%20Z%22%20fill%3D%22%23F5F5F5%22%3E%3C%2Fpath%3E%3C%2Fg%3E%3C%2Fsvg%3E');
    background-position: center center;
    background-repeat: no-repeat;
}
a.file:hover, a.file:focus {background-color: #4c4c4c;}
a picture {
    display: contents;
}
a img {
    display: block;
    object-fit: cover;
    width: 100%;
    height: 100%;
    transition: filter 0.2s ease;
}
a:hover img,
a:focus img {
    filter: brightness(1.1);
}
a span {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 5px;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    background: rgba(0, 0, 0, .5);
    color: #fff;
    -webkit-backdrop-filter: blur(30px);
    backdrop-filter: blur(30px);
}
footer {
    padding: 10px;
    font-size: 16px;
    text-align: center;
    color: #777;
}
.clear {clear: both;}
"""

    size = int(os.environ.get('THUMBNAIL_SIZE', '200'))
    styles = styles.replace('{SIZE}', str(size))

    if _env_bool(os.environ.get('GALLERY_LABELS_ONLY_ON_HOVER', 'true')):
        styles += """
a.image span {
    opacity: 0;
    transition: opacity 0.2s ease;
}
a.image:hover span,
a.image:focus span {
    opacity: 1;
}
"""

    if _env_bool(os.environ.get('GALLERY_JUSTIFIED', 'false')):
        styles += """
.container {
    max-width: none !important;
}
.jg-entry:not(.jg-entry-visible) {
    position: static !important;
}
.justified-gallery:has(.jg-entry:not(.jg-entry-visible)) {
    min-height: 100vh;
}
.justified-gallery > a.jg-entry-visible > picture > img {
    position: absolute;
    top: 50%;
    left: 50%;
    margin: 0;
    padding: 0;
    border: none;
}
.justified-gallery > a:not(.jg-entry-visible) {
    position: absolute !important;
    opacity: 1 !important;
    bottom: 0;
}
.justified-gallery > .jg-entry-visible > picture > img {
    opacity: 1;
    transition: opacity 500ms ease-in;
}
"""

    c = 3
    while (size + 6) * c <= 3840:
        styles += """
@media only screen and (min-width: {COL}px) {
    .container{
        max-width: {COL}px;
    }
}
""".replace('{COL}', str((size + 6) * c))
        c += 1

        styles += """
@media only screen and (max-width: {MW}px) {
    .container {
        max-width: none !important;
    }
    .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax({CW}px, 1fr));
        gap: 2px;
    }
    a.dir,
    a.image,
    a.file {
        float: none;
        width: 100%;
        height: auto;
        aspect-ratio: 1/1;
        margin: 0;
        border: none;
        outline: none;
    }
    a.file {
        background-size: 32px 39px;
    }
}""".replace('{MW}', str((size + 6) * 4)).replace('{CW}', str((size / 2) + 6))

    dark = os.environ.get('GALLERY_DARK_THEME', 'auto')
    if dark != 'auto':
        dark = _env_bool(dark)
    if dark:
        if dark == 'auto':
            styles += "@media only screen and (prefers-color-scheme: dark) {"

        styles += """
body {
    background: #111;
    color: #ccc;
}
a.dir, a.image, a.file {
    border-color: #000;
    outline-color: #222;
    background-color: #222;
}
a.dir:hover, a.dir:focus, a.image:hover, a.image:focus, a.file:hover, a.file:focus {
    outline-color: #444;
}
a.dir:focus, a.dir:hover {
    background-color: #333;
}
"""
        if dark == 'auto':
            styles += "}"

    return styles


def natural_sort_key(s):
    def convert(text: str):
        return int(text) if text.isdigit() else text.lower()

    return [convert(c) for c in re.split(r'(\d+)', s)]


def sorteddir(entries: list[os.DirEntry], natural: bool = True):
    if natural:
        return sorted(entries, key=lambda entry: natural_sort_key(entry.name))
    else:
        return sorted(entries, key=lambda entry: entry.name)


def thumb_dir():
    if not _env_bool(os.environ.get('THUMBNAIL_CACHE', 'true')):
        return None

    thumbdir = os.environ.get('THUMBNAIL_DIRECTORY')
    if thumbdir:
        root = os.path.expanduser(thumbdir)
        return root
    else:
        root = os.path.join(os.path.expanduser(
            os.environ.get('GALLERY_DIRECTORY', '.')), '.thm')
        os.makedirs(root, exist_ok=True)
        return '.thm'


def _pregenerate_target_paths(spec: str, root_dir: str) -> list[str]:
    norm = spec.strip()
    if not norm:
        return []

    # Boolean true means: recursively generate for the entire gallery directory.
    parsed = _env_bool(norm)
    if parsed is True:
        return [root_dir]
    if parsed is False:
        return []

    targets = []
    for raw in _split_csv(norm):
        candidate = os.path.abspath(os.path.join(
            root_dir, os.path.expanduser(raw)))
        if os.path.commonpath([candidate, root_dir]) != root_dir:
            continue
        if os.path.exists(candidate):
            targets.append(candidate)
    return targets


def _iter_pregenerate_dirs(path: str):
    if os.path.isdir(path):
        for root, dirs, _ in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            yield root


def _save_directory_thumbnail(directory: str, cacheabs: str, size: int, fmt: str, image_exts: set[str]):
    if os.path.exists(cacheabs):
        return

    os.makedirs(os.path.dirname(cacheabs), exist_ok=True)
    thm = PIL.Image.new('RGBA', (size, size), (0, 0, 0, 0))
    count = 0
    with os.scandir(directory) as entries:
        for entry in sorteddir([e for e in entries if not e.name.startswith('.') and e.is_file()]):
            ext = entry.name.rpartition('.')[2].lower()
            if ext not in image_exts:
                continue
            try:
                with thumbnail_source_image(entry.path, size) as sub:
                    sub = cropped_thumbnail(sub, (size // 2, size // 2))
                    x = count % 2 * size // 2
                    y = (count // 2) * (size // 2)
                    thm.paste(sub, (x, y))
                    count += 1
                    if count >= 4:
                        break
            except Exception:
                continue
    thm.save(cacheabs, fmt, quality=70)


def _iter_pregenerate_files(path: str, image_exts: set[str]):
    if os.path.isfile(path):
        if path.rpartition('.')[2].lower() in image_exts:
            yield path
        return

    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                if name.startswith('.'):
                    continue
                ext = name.rpartition('.')[2].lower()
                if ext in image_exts:
                    yield os.path.join(root, name)


def _save_thumbnail_variant(src: str, cacheabs: str, size: int, justified: bool, fmt: str):
    if os.path.exists(cacheabs):
        return

    os.makedirs(os.path.dirname(cacheabs), exist_ok=True)
    with thumbnail_source_image(src, size) as thm:
        thm = layout_thumbnail(thm, size, justified)
        thm.save(cacheabs, fmt, quality=70)


def pregenerate_thumbnails():
    spec = os.environ.get('GALLERY_PREGENERATE_THUMBNAILS', '').strip()
    if not spec:
        return

    cachedir = thumb_dir()
    if not cachedir:
        return

    root_dir = os.path.abspath(os.path.expanduser(
        os.environ.get('GALLERY_DIRECTORY', '.')))
    targets = _pregenerate_target_paths(spec, root_dir)
    if not targets:
        return

    img_exts = {'jpg', 'jpeg', 'jpe', 'jfif', 'png', 'gif', 'bmp', 'webp'}
    if heif_support:
        img_exts.update({'heif', 'heic'})
    if avif_support:
        img_exts.add('avif')
    if ffmpeg:
        img_exts.update({'mp4', 'm4v', 'webm'})
    if stl_thumb or blender:
        img_exts.update(ext.lstrip('.') for ext in STL_THUMB_MODEL_EXTS)
    if blender:
        img_exts.update(ext.lstrip('.') for ext in BLENDER_ONLY_MODEL_EXTS)

    image_exts = set(_split_csv(os.environ.get(
        'IMAGE_EXTS', ','.join(sorted(img_exts)))))
    size = int(os.environ.get('THUMBNAIL_SIZE', '200'))
    justified = _env_bool(os.environ.get('GALLERY_JUSTIFIED', 'false')) is True
    mode_suffix = '-j' if justified else ''

    for target in targets:
        for directory in _iter_pregenerate_dirs(target):
            sha1 = hashlib.sha1(directory.encode()).hexdigest()
            webp_cache = os.path.abspath(
                f'{cachedir}/{sha1}{mode_suffix}.webp')
            try:
                _save_directory_thumbnail(
                    directory, webp_cache, size, 'webp', image_exts)
                if avif_support:
                    avif_cache = os.path.abspath(
                        f'{cachedir}/{sha1}{mode_suffix}.avif')
                    _save_directory_thumbnail(
                        directory, avif_cache, size, 'avif', image_exts)
            except Exception:
                continue

        for src in _iter_pregenerate_files(target, image_exts):
            sha1 = hashlib.sha1(src.encode()).hexdigest()
            webp_cache = os.path.abspath(
                f'{cachedir}/{sha1}{mode_suffix}.webp')
            try:
                _save_thumbnail_variant(
                    src, webp_cache, size, justified, 'webp')
                if avif_support:
                    avif_cache = os.path.abspath(
                        f'{cachedir}/{sha1}{mode_suffix}.avif')
                    _save_thumbnail_variant(
                        src, avif_cache, size, justified, 'avif')
            except Exception:
                continue


def maybe_start_pregenerate_subprocess():
    spec = os.environ.get('GALLERY_PREGENERATE_THUMBNAILS', '').strip()
    if not spec:
        return
    if _env_bool(spec) is False:
        return

    cmd = [sys.executable, os.path.abspath(__file__), '--pregenerate-run']
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cropped_thumbnail(img: PIL.Image.Image, size):
    width, height = img.size
    smaller_side = min(width, height)

    left = (width - smaller_side) // 2
    top = (height - smaller_side) // 2
    right = (width + smaller_side) // 2
    bottom = (height + smaller_side) // 2

    result = img.crop((left, top, right, bottom))
    result.thumbnail(size)
    return result


def layout_thumbnail(img: PIL.Image.Image, size: int, justified: bool = False):
    if not justified:
        return cropped_thumbnail(img, (size, size))

    source_width, source_height = img.size
    if source_height <= 0:
        return cropped_thumbnail(img, (size, size))

    scale = size / source_height
    target_width = max(1, round(source_width * scale))

    try:
        max_width_multiplier = int(os.environ.get(
            'JUSTIFIED_THUMBNAIL_MAX_WIDTH_MULTIPLIER', '4'))
    except ValueError:
        max_width_multiplier = 4
    max_width_multiplier = max(1, max_width_multiplier)
    max_target_width = max(1, size * max_width_multiplier)
    target_width = min(target_width, max_target_width)

    return img.resize((target_width, size), PIL.Image.Resampling.LANCZOS)


def ffmpeg_thumb(src: str):
    if not ffmpeg:
        raise RuntimeError('ffmpeg is not available')
    root = thumb_dir() or tempfile.gettempdir()
    os.makedirs(root, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='ffmpeg-thumb-', suffix='.webp', dir=root, delete=False) as f:
        outfile = f.name
    cmd = [
        ffmpeg,
        '-y',
        '-i', src,
        '-ss', '0',
        '-t', '5',
        '-vf', 'fps=1/1',
        '-q:v', '75',
        '-f', 'webp',
        outfile
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not os.path.isfile(outfile):
        if os.path.exists(outfile):
            os.unlink(outfile)
        raise RuntimeError(
            f'ffmpeg failed (exit {result.returncode}): '
            + result.stderr.decode('utf-8', errors='replace').strip())
    return outfile


def stl_thumb_render(src: str, size: int):
    if not stl_thumb:
        raise RuntimeError('stl-thumb is not available')

    root = thumb_dir() or tempfile.gettempdir()
    os.makedirs(root, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='stl-thumb-', suffix='.png', dir=root, delete=False) as f:
        outfile = f.name
    cmd = [
        stl_thumb,
        '--size', str(max(1, size)),
        src,
        outfile,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not os.path.isfile(outfile):
        if os.path.exists(outfile):
            os.unlink(outfile)
        raise RuntimeError(
            f'stl-thumb failed (exit {result.returncode}): '
            + result.stderr.decode('utf-8', errors='replace').strip())
    return outfile


def blender_thumb_render(src: str, size: int):
    if not blender:
        raise RuntimeError('blender is not available')

    root = thumb_dir() or tempfile.gettempdir()
    os.makedirs(root, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='blender-thumb-', suffix='.png', dir=root, delete=False) as f:
        outfile = f.name
    cmd = [
        blender,
        '-b',
        '--factory-startup',
        '-P',
        blender_thumb_script,
        '--',
        '--input', src,
        '--output', outfile,
        '--size', str(max(1, size)),
    ]
    xvfb_run = shutil.which('xvfb-run')
    if xvfb_run:
        cmd = [xvfb_run, '-a'] + cmd

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not os.path.isfile(outfile):
        if os.path.exists(outfile):
            os.unlink(outfile)
        raise RuntimeError(
            f'blender thumbnail failed (exit {result.returncode}): '
            + result.stderr.decode('utf-8', errors='replace').strip())
    return outfile


@contextmanager
def thumbnail_source_image(src: str, size: int):
    tmp = None
    lower_src = src.lower()
    if lower_src.endswith(VIDEO_EXTS):
        if not ffmpeg:
            raise RuntimeError('ffmpeg is not available')
        tmp = ffmpeg_thumb(src)
    elif lower_src.endswith(STL_THUMB_MODEL_EXTS):
        if stl_thumb:
            try:
                tmp = stl_thumb_render(src, size)
            except Exception:
                if blender:
                    tmp = blender_thumb_render(src, size)
                else:
                    raise
        elif blender:
            tmp = blender_thumb_render(src, size)
    elif lower_src.endswith(BLENDER_ONLY_MODEL_EXTS) and blender:
        tmp = blender_thumb_render(src, size)

    try:
        with PIL.Image.open(tmp or src) as img:
            yield img
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


class GalleryRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.title = os.environ.get('GALLERY_TITLE', 'Gallery')
        img_exts = 'jpg,jpeg,jpe,jfif,png,gif,bmp,webp'
        file_exts = 'txt,zip,rar,7z,svg,m4a,mp3,ogg'
        if heif_support:
            img_exts += ',heif,heic'
        else:
            file_exts += ',heif,heic'
        if avif_support:
            img_exts += ',avif'
        else:
            file_exts += ',avif'
        if ffmpeg:
            img_exts += ',mp4,m4v,webm'
        else:
            file_exts += ',mp4,m4v,webm'
        if stl_thumb:
            img_exts += ',' + ','.join(ext.lstrip('.') for ext in STL_THUMB_MODEL_EXTS)
        elif blender:
            img_exts += ',' + ','.join(ext.lstrip('.') for ext in STL_THUMB_MODEL_EXTS)
        else:
            file_exts += ',' + ','.join(ext.lstrip('.') for ext in STL_THUMB_MODEL_EXTS)

        if blender:
            img_exts += ',' + ','.join(ext.lstrip('.') for ext in BLENDER_ONLY_MODEL_EXTS)
        else:
            file_exts += ',' + ','.join(ext.lstrip('.') for ext in BLENDER_ONLY_MODEL_EXTS)
        self.image_exts = os.environ.get('IMAGE_EXTS', img_exts).split(',')
        self.file_exts = os.environ.get('FILE_EXTS', file_exts).split(',')
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = self.translate_path(self.path)

        if self.path[0:6] == '/.thm/':
            return self.handle_thumb(path)
        elif path[-1] != '/':
            return super().do_GET()
        else:
            return self.handle_dir(path)

    def _read_dir(self, path) -> tuple[list[os.DirEntry], list[os.DirEntry], list[os.DirEntry]]:
        directories = []
        images = []
        files = []

        with os.scandir(path) as it:
            for entry in it:
                if entry.name.startswith('.'):
                    continue
                if entry.is_file():
                    ext = entry.name.rpartition('.')[2]
                    if ext.lower() in self.image_exts:
                        images.append(entry)
                    elif ext.lower() in self.file_exts:
                        files.append(entry)
                elif entry.is_dir():
                    directories.append(entry)

        return (sorteddir(directories), sorteddir(images), sorteddir(files))

    def handle_dir(self, directory):
        global e
        try:
            directories, images, files = self._read_dir(directory)
            justified = _env_bool(os.environ.get(
                'GALLERY_JUSTIFIED', 'false')) is True
            thumb_size = int(os.environ.get('THUMBNAIL_SIZE', '200'))

            breadcrumbs = ""
            rel = os.path.relpath(directory, self.directory)
            if len(rel) > 1:
                breadcrumbs += f"""
<p class="breadcrumbs"><a href="/">{esc(self.title)}</a> /
"""
                pathpart = '/'
                for part in rel.strip('/').split('/'):
                    pathpart += f'{part}/'
                    breadcrumbs += f' <a href="{qe(pathpart)}">{esc(part)}</a> /'

                breadcrumbs += '</p>'

            response_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{esc(self.title)}</title>
    <meta name="viewport" content="width=device-width,maximum-scale=1">
    <style type="text/css">
    {css()}
    </style>
"""
            if justified:
                response_content += """
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@slithy/justified-gallery@4.0.0/dist/index.css">
"""
            response_content += f"""
</head>
<body>
    <div class="container">
        {breadcrumbs}"""

            dir_tiles = ""
            for d in directories:
                thm_base = f'/.thm/{qe(rel)}/{qe(d.name)}'
                avif_source = f'<source srcset="{thm_base}?fmt=avif 1x, {thm_base}?fmt=avif&amp;scale=2 2x" type="image/avif">\n        ' if avif_support else ''
                dir_tiles += f"""
<a class="dir" href="{qe(d.name)}" title="{esc(d.name)}">
    <picture>
        {avif_source}<img src="{thm_base}" srcset="{thm_base}?scale=2 2x" loading="lazy" decoding="async" alt>
    </picture>
    <span>{esc(d.name)}</span>
</a>
"""
            image_tiles = ""
            for image in images:
                thm_base = f'/.thm/{qe(rel)}/{qe(image.name)}'
                avif_source = f'<source srcset="{thm_base}?fmt=avif 1x, {thm_base}?fmt=avif&amp;scale=2 2x" type="image/avif">\n        ' if avif_support else ''
                image_tiles += f"""
<a class="image" href="{qe(image.name)}" title="{esc(image.name)}">
    <picture>
        {avif_source}<img src="{thm_base}" srcset="{thm_base}?scale=2 2x" loading="lazy" decoding="async" alt>
    </picture>
    <span>{esc(image.name)}</span>
</a>
"""

            file_tiles = ""
            for file in files:
                file_tiles += f"""
<a class="file" href="{qe(file.name)}" title="{esc(file.name)}">
    <span>{esc(file.name)}</span>
</a>
"""

            if justified:
                min_width = (thumb_size + 6) * 4
                if dir_tiles:
                    response_content += f'<div class="grid">{dir_tiles}</div>'
                response_content += f'<div class="grid" id="jg-queue">{image_tiles}</div>'
                if file_tiles:
                    response_content += f'<div class="grid">{file_tiles}</div>'
                response_content += f"""
    <script type="module">
        import {{ justifiedGallery }} from 'https://cdn.jsdelivr.net/npm/@slithy/justified-gallery@4.0.0/+esm';
        const queue = document.getElementById('jg-queue');
        if (queue && window.matchMedia('(min-width: {min_width}px)').matches) {{
            queue.style.opacity = '0';
            queue.style.pointerEvents = 'none';
            const jgEl = document.createElement('div');
            jgEl.className = 'justified-gallery';
            queue.parentNode.insertBefore(jgEl, queue);
            const jg = justifiedGallery(jgEl, {{
                rowHeight: {thumb_size},
                margins: 4,
                imgSelector: 'img',
                captions: false,
            }});
            const observer = new IntersectionObserver((entries) => {{
                let added = false;
                for (const entry of entries) {{
                    if (entry.isIntersecting) {{
                        observer.unobserve(entry.target);
                        const img = entry.target.querySelector('img');
                        if (img) img.removeAttribute('loading');
                        jgEl.appendChild(entry.target);
                        added = true;
                    }}
                }}
                if (added) jg.addEntries();
            }}, {{ rootMargin: '400px 0px 0px 0px' }});
            for (const el of queue.querySelectorAll('a.image')) {{
                observer.observe(el);
            }}
        }}
    </script>
"""
            else:
                response_content += f'<div class="grid">{dir_tiles}{image_tiles}{file_tiles}</div>'

            response_content += """
        <div class="clear"></div>
        <footer>{COUNT} items</footer>
    </div>
</body>
</html>
""".replace('{COUNT}', str(len(directories) + len(images) + len(files)))

            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            self.wfile.write(response_content.encode())
        except PermissionError:
            self.send_error(403)
        except Exception as e:
            self.send_error(500, 'Internal Server Error', str(e))

    def handle_thumb(self, path: str):
        src = path.replace('/.thm', '')
        sha1 = hashlib.sha1(src.encode()).hexdigest()
        suffix = ''
        size = int(os.environ.get('THUMBNAIL_SIZE', '200'))
        justified = _env_bool(os.environ.get(
            'GALLERY_JUSTIFIED', 'false')) is True
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if qs.get('scale'):
            scale = int(qs.get('scale', [0])[0])
            suffix = f'@{scale}x'
            size *= scale
        mode_suffix = '-j' if justified else ''

        fmt = 'avif' if (qs.get('fmt', [''])[0]
                         == 'avif' and avif_support) else 'webp'
        mime_type = f'image/{fmt}'

        cachedir = thumb_dir()
        try:
            if cachedir:
                cachefn = f'{sha1}{mode_suffix}{suffix}.{fmt}'
                cacheabs = os.path.abspath(f'{cachedir}/{cachefn}')

                if not os.path.isfile(cacheabs):
                    if os.path.isdir(src):
                        self.save_dir_thumb(src, cacheabs, size, fmt)
                    else:
                        with thumbnail_source_image(src, size) as thm:
                            thm = layout_thumbnail(thm, size, justified)
                            thm.save(cacheabs, fmt, quality=70)

                if cachedir == '.thm':
                    self.path = f'.thm/{cachefn}'
                    return super().do_GET()
                else:
                    target = open(cacheabs, 'rb')

            else:
                target = io.BytesIO()
                if os.path.isdir(src):
                    self.save_dir_thumb(src, target, size, fmt)
                else:
                    with thumbnail_source_image(src, size) as thm:
                        thm = layout_thumbnail(thm, size, justified)
                        thm.save(target, fmt, quality=70)

            self.send_response(200)
            self.send_header('Content-Type', mime_type)
            self.send_header('Cache-Control', 'max-age=86400')
            self.end_headers()
            try:
                target.seek(0)
                self.copyfile(target, self.wfile)
            finally:
                target.close()

        except PermissionError:
            self.send_error(403)

    def save_dir_thumb(self, directory: str, outfile, size: int, fmt: str = 'webp'):
        thm = PIL.Image.new('RGBA', (size, size), (0, 0, 0, 0))
        _, images, _ = self._read_dir(directory)
        count = 0
        for img in images:
            if count >= 4:
                break
            try:
                with thumbnail_source_image(img.path, size) as sub:
                    sub = cropped_thumbnail(sub, (size // 2, size // 2))
                    x = count % 2 * size // 2
                    y = (count // 2) * (size // 2)
                    thm.paste(sub, (x, y))
                    count += 1
            except Exception:
                pass
        thm.save(outfile, fmt, quality=70)


def args_to_env():
    parser = argparse.ArgumentParser()
    parser.add_argument('--address')
    parser.add_argument('-p', '--port', type=int)
    parser.add_argument('-d', '--directory')
    parser.add_argument(
        '--pregenerate-thumbnails',
        nargs='?',
        const='true',
        help='pre-generate thumbnails recursively in a subprocess; true=all, or pass csv paths',
    )
    parser.add_argument('--pregenerate-run',
                        action='store_true', help=argparse.SUPPRESS)

    args = parser.parse_args()
    if args.address:
        os.environ['GALLERY_HOST'] = args.address
    if args.port:
        os.environ['GALLERY_PORT'] = str(args.port)
    if args.directory:
        os.environ['GALLERY_DIRECTORY'] = args.directory
    if args.pregenerate_thumbnails is not None:
        os.environ['GALLERY_PREGENERATE_THUMBNAILS'] = args.pregenerate_thumbnails
    if args.pregenerate_run:
        os.environ['GALLERY_PREGENERATE_RUN'] = 'true'


def main():
    args_to_env()

    if _env_bool(os.environ.get('GALLERY_PREGENERATE_RUN', 'false')):
        pregenerate_thumbnails()
        return

    maybe_start_pregenerate_subprocess()
    directory = os.path.expanduser(os.environ.get('GALLERY_DIRECTORY', '.'))

    class GalleryServer(http.server.ThreadingHTTPServer):
        def finish_request(self, request, client_address):
            GalleryRequestHandler(request, client_address, self,
                                  directory=directory)

    host = os.environ.get('GALLERY_HOST', '127.0.0.1')
    port = int(os.environ.get('GALLERY_PORT', '8000'))
    with GalleryServer((host, port), GalleryRequestHandler) as httpd:
        host, port = httpd.socket.getsockname()[:2]
        url_host = f'[{host}]' if ':' in host else host
        print(
            f"Serving HTTP on {host} port {port} "
            f"(http://{url_host}:{port}/) ..."
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received, exiting.")
            return


if __name__ == "__main__":
    main()
