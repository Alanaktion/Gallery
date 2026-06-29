package main

import (
	"bytes"
	"image"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	webpenc "github.com/gen2brain/webp"
)

var ffmpegExts = map[string]bool{
	".avif": true,
	".mp4":  true,
	".mov":  true,
	".avi":  true,
	".mkv":  true,
	".webm": true,
	".flv":  true,
	".wmv":  true,
	".m4v":  true,
	".mpg":  true,
	".mpeg": true,
}

var hasFFmpeg bool

func checkFFmpeg() bool {
	if _, err := exec.LookPath("ffmpeg"); err == nil {
		return true
	}
	return false
}

func isFFmpegFormat(path string) bool {
	return ffmpegExts[strings.ToLower(filepath.Ext(path))]
}

func (g *Gallery) GenerateFFmpegThumbnail(relPath string) (string, error) {
	if !g.ffmpegOK {
		return "", os.ErrNotExist
	}

	thumbPath := thumbnailPath(relPath, g.CacheDir)
	srcPath := filepath.Join(g.Root, relPath)

	srcStat, err := os.Stat(srcPath)
	if err != nil {
		return "", err
	}

	if cached, err := os.Stat(thumbPath); err == nil {
		if !srcStat.ModTime().After(cached.ModTime()) {
			return thumbPath, nil
		}
	}

	var buf bytes.Buffer
	var stderr bytes.Buffer

	cmd := exec.Command("ffmpeg",
		"-i", srcPath,
		"-vframes", "1",
		"-f", "image2pipe",
		"-vcodec", "mjpeg",
		"-q:v", "3",
		"-")
	cmd.Stdout = &buf
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return "", err
	}

	img, _, err := image.Decode(bytes.NewReader(buf.Bytes()))
	if err != nil {
		return "", err
	}

	img = resizeImage(img, g.ImageHeight, g.MaxAspect)

	if err := os.MkdirAll(filepath.Dir(thumbPath), 0755); err != nil {
		return "", err
	}

	f, err := os.Create(thumbPath)
	if err != nil {
		return "", err
	}
	defer f.Close()

	if err := webpenc.Encode(f, img, webpenc.Options{Quality: g.Quality}); err != nil {
		return "", err
	}

	return thumbPath, nil
}
