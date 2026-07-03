FROM golang:1.24-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /gallery .

FROM debian:bookworm-slim

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

ENTRYPOINT ["gallery"]
