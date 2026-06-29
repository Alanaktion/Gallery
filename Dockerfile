FROM golang:1.24-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /gallery .

FROM alpine:3.21

RUN apk add --no-cache ffmpeg ca-certificates

COPY --from=builder /gallery /usr/local/bin/gallery

EXPOSE 8080
VOLUME ["/data"]

ENV GALLERY_ROOT=/data
ENV GALLERY_PORT=8080
ENV GALLERY_IMAGE_HEIGHT=250
ENV GALLERY_MAX_ASPECT=2.0
ENV GALLERY_CACHE_DIR=/tmp/gallery-cache
ENV GALLERY_TITLE=Gallery
ENV GALLERY_QUALITY=85

ENTRYPOINT ["gallery"]
