FROM golang:1.24-trixie AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /gallery .

FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/rclip-env && \
    /opt/rclip-env/bin/pip install --no-cache-dir rclip

ENV PATH="/opt/rclip-env/bin:${PATH}"

COPY --from=builder /gallery /usr/local/bin/gallery

EXPOSE 8080
VOLUME ["/files"]

ENV GALLERY_ROOT=/files
ENV GALLERY_PORT=8080
ENV GALLERY_IMAGE_HEIGHT=250
ENV GALLERY_MAX_ASPECT=2.0
ENV GALLERY_CACHE_DIR=/tmp/gallery-cache
ENV GALLERY_TITLE=Gallery
ENV GALLERY_QUALITY=85
ENV GALLERY_FILE_EXTS=.zip,.rar,.7z,.tar,.gz,.tgz,.bz2,.xz,.pdf,.txt,.md,.doc,.docx,.odt,.rtf,.epub,.csv,.json,.xml,.gpx,.log,.nfo,.srt,.vtt,.yaml,.yml

ENV RCLIP_DATADIR=/tmp/gallery-cache/rclip
ENV RCLIP_MODEL_CACHE_DIR=/tmp/gallery-cache/rclip-models

ENTRYPOINT ["gallery"]
