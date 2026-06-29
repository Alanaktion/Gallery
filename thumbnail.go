package main

import (
	"crypto/sha256"
	"fmt"
	"image"
	"image/jpeg"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/image/draw"
	"golang.org/x/image/webp"
)

var nativeExts = map[string]bool{
	".jpg":  true,
	".jpeg": true,
	".png":  true,
	".gif":  true,
	".bmp":  true,
	".tiff": true,
	".tif":  true,
	".webp": true,
}

var mediaExts = map[string]bool{}

func init() {
	for k, v := range nativeExts {
		mediaExts[k] = v
	}
	for k, v := range ffmpegExts {
		mediaExts[k] = v
	}
}

func isNativeImage(path string) bool {
	return nativeExts[strings.ToLower(filepath.Ext(path))]
}

func thumbnailPath(relPath, cacheDir string) string {
	h := sha256.Sum256([]byte(relPath))
	hash := fmt.Sprintf("%x", h[:16])
	dir := filepath.Join(cacheDir, hash[:2])
	return filepath.Join(dir, hash+".jpg")
}

func (g *Gallery) GenerateThumbnail(relPath string) (string, error) {
	thumbPath := thumbnailPath(relPath, g.CacheDir)
	srcPath := filepath.Join(g.Root, relPath)
	ext := strings.ToLower(filepath.Ext(relPath))

	srcStat, err := os.Stat(srcPath)
	if err != nil {
		return "", err
	}

	if cached, err := os.Stat(thumbPath); err == nil {
		if !srcStat.ModTime().After(cached.ModTime()) {
			return thumbPath, nil
		}
	}

	var img image.Image

	if ext == ".webp" {
		img, err = decodeWebP(srcPath)
	} else {
		img, err = decodeStdImage(srcPath)
	}
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

	if err := jpeg.Encode(f, img, &jpeg.Options{Quality: g.Quality}); err != nil {
		return "", err
	}

	return thumbPath, nil
}

func decodeStdImage(path string) (image.Image, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	img, _, err := image.Decode(f)
	return img, err
}

func decodeWebP(path string) (image.Image, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	return webp.Decode(f)
}

func resizeImage(img image.Image, height int, maxAspect float64) image.Image {
	bounds := img.Bounds()
	srcW := bounds.Dx()
	srcH := bounds.Dy()

	if srcH == 0 {
		return img
	}

	newH := height
	newW := srcW * height / srcH

	maxW := int(float64(height) * maxAspect)
	if newW > maxW {
		newW = maxW
	}
	if newW < 1 {
		newW = 1
	}
	if newH < 1 {
		newH = 1
	}

	dst := image.NewRGBA(image.Rect(0, 0, newW, newH))
	draw.BiLinear.Scale(dst, dst.Bounds(), img, bounds, draw.Over, nil)
	return dst
}
