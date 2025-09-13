import argparse
import hashlib
import http.server
import io
import os
import re
import shutil
import subprocess
import tempfile
import PIL.Image
import urllib.parse

from dotenv import load_dotenv
from html import escape as esc

load_dotenv()

ffmpeg = os.environ.get('FFMPEG_PATH', shutil.which('ffmpeg'))


_BOOLEAN_STATES = {'1': True, 'yes': True, 'true': True, 'on': True,
                   '0': False, 'no': False, 'false': False, 'off': False}

def _env_bool(value: str):
    if value.lower() not in _BOOLEAN_STATES:
        return value
    return _BOOLEAN_STATES[value.lower()]


def qe(val: str):
    return esc(urllib.parse.quote(val))


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


def ffmpeg_thumb(src: str):
    sha1 = hashlib.sha1(src.encode()).hexdigest()
    if _env_bool(os.environ.get('THUMBNAIL_CACHE', 'true')):
        root = os.path.join(os.path.expanduser(os.environ.get('GALLERY_DIRECTORY', '.')), '.thm')
        os.makedirs(root, exist_ok=True)
    else:
        root = tempfile.gettempdir()
    outfile = os.path.join(root, f'{sha1}_ffmpeg.webp')
    if os.path.exists(outfile):
        return outfile
    cmd = [
        'ffmpeg',
        '-i', src,
        '-ss', '0',
        '-t', '5',
        '-vf', 'fps=1/1',
        '-q:v', '75',
        '-f', 'webp',
        outfile
    ]
    subprocess.run(cmd, check=True)
    return outfile


class GalleryRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.title = os.environ.get('GALLERY_TITLE', 'Gallery')
        img_exts = 'jpg,jpeg,jpe,jfif,png,gif,bmp,webp'
        file_exts = 'txt,zip,rar,7z,heif,heic,svg,m4a,mp3,ogg'
        if ffmpeg:
            img_exts += ',mp4,m4v,webm'
        else:
            file_exts += ',mp4,m4v,webm'
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
</head>
<body>
    <div class="container">
        <div class="grid">{breadcrumbs}"""

            for d in directories:
                response_content += f"""
<a class="dir" href="{qe(d.name)}" title="{esc(d.name)}">
    <img type="image/webp" src="/.thm/{qe(rel)}/{qe(d.name)}" srcset="/.thm/{qe(rel)}/{qe(d.name)}?scale=2 2x" loading="lazy" decoding="async" alt>
    <span>{esc(d.name)}</span>
</a>
"""
            for image in images:
                response_content += f"""
<a class="image" href="{qe(image.name)}" title="{esc(image.name)}">
    <img type="image/webp" src="/.thm/{qe(rel)}/{qe(image.name)}" srcset="/.thm/{qe(rel)}/{qe(image.name)}?scale=2 2x" loading="lazy" decoding="async" alt>
    <span>{esc(image.name)}</span>
</a>
"""

            for file in files:
                response_content += f"""
<a class="file" href="{qe(file.name)}" title="{esc(file.name)}">
    <span>{esc(file.name)}</span>
</a>
"""

            response_content += """
        </div>
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
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if qs.get('scale'):
            scale = int(qs.get('scale', [0])[0])
            suffix = f'@{scale}x'
            size *= scale
        cachefn = f'.thm/{sha1}{suffix}.webp'

        do_cache = _env_bool(os.environ.get('THUMBNAIL_CACHE', 'true'))

        try:
            if do_cache:
                cacheabs = self.translate_path(cachefn)
                cachedir = self.translate_path('.thm/')
                if not os.path.isdir(cachedir):
                    os.makedirs(cachedir, exist_ok=True)

                if not os.path.isfile(cacheabs):
                    if os.path.isdir(src):
                        self.save_dir_thumb(src, cacheabs, size)
                    else:
                        if path.endswith(('.mp4', '.m4v', '.webm')):
                            vimg = ffmpeg_thumb(src)
                            thm = PIL.Image.open(vimg)
                            os.unlink(vimg)
                        else:
                            thm = PIL.Image.open(src)
                        thm = cropped_thumbnail(thm, (size, size))
                        thm.save(cacheabs, 'webp', quality=70)

                self.path = cachefn
                return super().do_GET()

            else:
                target = io.BytesIO()
                if os.path.isdir(src):
                    self.save_dir_thumb(src, target, size)
                else:
                    if path.endswith(('.mp4', '.m4v', '.webm')):
                        vimg = ffmpeg_thumb(src)
                        thm = PIL.Image.open(vimg)
                        os.unlink(vimg)
                    else:
                        thm = PIL.Image.open(src)
                    thm = cropped_thumbnail(thm, (size, size))
                    thm.save(target, 'webp', quality=70)

            self.send_response(200)
            self.send_header('Content-type', 'image/webp')
            self.end_headers()
            try:
                target.seek(0)
                self.copyfile(target, self.wfile)
            finally:
                target.close()

        except PermissionError:
            self.send_error(403)

    def save_dir_thumb(self, directory: str, outfile, size: int):
        thm = PIL.Image.new('RGBA', (size, size), (0, 0, 0, 0))
        _, images, _ = self._read_dir(directory)
        # TODO: iterate through all images, skipping unsupported files (videos+), up to 4 supported files
        for i in range(min(4, len(images))):
            img = images[i]
            sub = PIL.Image.open(img.path)
            sub = cropped_thumbnail(sub, (size // 2, size // 2))
            x = i % 2 * size // 2
            y = (i // 2) * (size // 2)
            thm.paste(sub, (x, y))
        thm.save(outfile, 'webp', quality=70)


def args_to_env():
    parser = argparse.ArgumentParser()
    parser.add_argument('--address')
    parser.add_argument('-p', '--port', type=int)
    parser.add_argument('-d', '--directory')

    args = parser.parse_args()
    if args.address:
        os.environ['GALLERY_HOST'] = args.address
    if args.port:
        os.environ['GALLERY_PORT'] = str(args.port)
    if args.directory:
        os.environ['GALLERY_DIRECTORY'] = args.directory


def main():
    args_to_env()
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
