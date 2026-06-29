# gallery-pro

A self-contained Go image gallery server. Scans a directory, generates cacheable thumbnails on demand, and renders a justified flexbox layout.

## Usage

### Standalone

```bash
export GALLERY_ROOT=/path/to/photos
go run .
```

### Docker

```bash
docker run -p 8080:8080 -v /path/to/photos:/files ghcr.io/alanaktion/gallery:go
```

### Docker Compose

```yaml
services:
  gallery:
    image: ghcr.io/alanaktion/gallery:go
    container_name: gallery
    ports:
      - "8080:8080"
    volumes:
      - /path/to/photos:/files
    environment:
      - GALLERY_TITLE=My Photos
      - GALLERY_IMAGE_HEIGHT=300
      - GALLERY_CACHE_DIR=/tmp/gallery-cache
    restart: unless-stopped
```

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `GALLERY_ROOT` | `/files` | Root directory to scan and serve |
| `GALLERY_PORT` | `8080` | HTTP listen port |
| `GALLERY_IMAGE_HEIGHT` | `250` | Fixed thumbnail height in pixels |
| `GALLERY_MAX_ASPECT` | `2.0` | Max width/height ratio for thumbnails |
| `GALLERY_CACHE_DIR` | `/tmp/gallery-cache` | Thumbnail cache directory |
| `GALLERY_TITLE` | `Gallery` | Page title shown in browser tab and breadcrumbs |
| `GALLERY_QUALITY` | `85` | JPEG thumbnail quality (1-100) |

## Formats

| Format | Decoder |
| --- | --- |
| JPEG / PNG / GIF | Go standard library |
| BMP / TIFF | `golang.org/x/image` |
| WebP | `golang.org/x/image/webp` |
| AVIF / Video (mp4, mov, mkv, etc.) | FFmpeg (runtime) |

FFmpeg is optional. When not available, AVIF and video thumbnails are skipped.

## Build

```bash
go build -o gallery .
```
