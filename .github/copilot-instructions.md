# Copilot Instructions

## Architecture

This is a **single-file photo gallery** with two parallel implementations that share the same feature set:

- **`gallery.php`** — PHP implementation, drop-in web server deployment
- **`gallery.py`** — Python implementation, self-hosted HTTP server using `http.server.SimpleHTTPRequestHandler`

Both serve the same HTML/CSS UI inline (no external template files) and handle thumbnails, subdirectory navigation, breadcrumbs, dark mode, and file listings.

## Running the Python Server

```bash
python3 gallery.py                  # serve current directory on port 8000
python3 gallery.py -d ~/Pictures    # specify a directory
python3 gallery.py -p 9000          # specify a port
```

Dependencies: `pip3 install Pillow python-dotenv pi-heif`

## Configuration (Python)

Configuration is via environment variables or a `.env` file in the cwd. See `.env.example` for all defaults. Key variables:

| Variable | Default | Notes |
|---|---|---|
| `GALLERY_TITLE` | `Gallery` | Page title |
| `GALLERY_JUSTIFIED` | `false` | Justified layout |
| `GALLERY_DARK_THEME` | `auto` | `auto`, `true`, `false` |
| `THUMBNAIL_SIZE` | `200` | Pixel size |
| `THUMBNAIL_CACHE` | `false` | Cache to disk |
| `THUMBNAIL_DIRECTORY` | `.thm` | Cache directory |
| `IMAGE_EXTS` | csv | Override detected image types |
| `FILE_EXTS` | csv | Override file types |

Optional system tools extend functionality when on `PATH`:
- **`ffmpeg`** — enables video thumbnail generation (mp4, m4v, webm)
- **`gltf_viewer`** — enables 3D model thumbnails (glTF, GLB); OBJ/STL are listed without thumbnails

## Configuration (PHP)

Config is in the `$config` array at the top of `gallery.php`. To avoid losing changes on updates, override in a separate `gallery-config.php` file (auto-included if present).

## Thumbnail System

Thumbnails are generated on-demand and keyed by SHA1 hash of the file path:
- **Python**: `hashlib.sha1(src.encode()).hexdigest()` where `src` is the filesystem path
- **PHP**: `sha1($dir . '/' . $name)` on sanitized path segments
- Cached as `{sha1}[mode_suffix][@scale].{fmt}` in the `.thm` directory
- Format negotiation: AVIF preferred when server supports it, fallback to WebP, then JPEG

Directory thumbnails are a 2×2 grid of the first 4 images in that directory.

## Security (PHP)

The PHP implementation explicitly protects against path traversal:
- `normalize_relative_path()` strips `..` segments and returns `null` on traversal attempts
- `resolve_path_in_base()` uses `realpath()` and prefix-checks against the configured base directory
- All user-supplied paths go through these functions before any filesystem access

## Docker

Two Docker variants, both published to `ghcr.io/alanaktion/gallery`:

- `latest` — built from `Dockerfile`, standard Python + ffmpeg + HEIF
- `gltf` — built from `Dockerfile.gltf`, adds Filament's `gltf_viewer` for 3D model rendering

CI pushes both tags on every push to `master` via `.github/workflows/docker.yml` (builds for Docker Hub and GHCR simultaneously).

Example volume layout: images in `/gallery`, thumbnail cache in `/thm`.

## Key Conventions

- **Hidden files** (names starting with `.`) are always excluded from listings in both implementations
- **Natural sort** is used for directory entries (numbers sorted numerically within filenames)
- **CSS is generated inline** — there are no external stylesheets; the Python `css()` function and PHP equivalent both inject CSS directly into the `<style>` tag using string replacement for dynamic values like `{SIZE}`
- **AVIF support is detected at startup** in Python (`_check_avif_support()`) and at the PHP level (`function_exists('imagecreatefromavif')`) — conditional `<source>` elements are only emitted when AVIF is available
- **Boolean env vars** in Python use `_env_bool()` which accepts `1/yes/true/on` and `0/no/false/off` (case-insensitive)
- The `qe()` helper in Python URL-encodes and HTML-escapes values for safe use in `href` attributes
