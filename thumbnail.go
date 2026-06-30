package main

import (
	"crypto/sha256"
	"fmt"
	"image"
	"image/color"
	"os"
	"path/filepath"
	"strings"

	webpenc "github.com/gen2brain/webp"
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
	return filepath.Join(dir, hash+".webp")
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

	if err := webpenc.Encode(f, img, webpenc.Options{Quality: g.Quality}); err != nil {
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

func cropCenterSquare(img image.Image, size int) image.Image {
	bounds := img.Bounds()
	w := bounds.Dx()
	h := bounds.Dy()
	side := w
	if h < side {
		side = h
	}
	offsetX := (w - side) / 2
	offsetY := (h - side) / 2

	dst := image.NewRGBA(image.Rect(0, 0, size, size))
	draw.BiLinear.Scale(dst, dst.Bounds(), img, image.Rect(offsetX, offsetY, offsetX+side, offsetY+side), draw.Over, nil)
	return dst
}

func (g *Gallery) GenerateFolderThumbnail(relPath string) (string, error) {
	thumbPath := thumbnailPath(relPath, g.CacheDir)
	dirPath := filepath.Join(g.Root, relPath)

	dirStat, err := os.Stat(dirPath)
	if err != nil {
		return "", err
	}

	entries, err := os.ReadDir(dirPath)
	if err != nil {
		return "", err
	}

	var mediaFiles []string
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || strings.HasPrefix(name, ".") {
			continue
		}
		rel := filepath.Join(relPath, name)
		if isMedia(rel) {
			mediaFiles = append(mediaFiles, rel)
			if len(mediaFiles) >= 4 {
				break
			}
		}
	}

	if cached, err := os.Stat(thumbPath); err == nil {
		cacheValid := !dirStat.ModTime().After(cached.ModTime())
		for _, mf := range mediaFiles {
			srcPath := filepath.Join(g.Root, mf)
			srcStat, err := os.Stat(srcPath)
			if err == nil && srcStat.ModTime().After(cached.ModTime()) {
				cacheValid = false
				break
			}
		}
		if cacheValid {
			return thumbPath, nil
		}
	}

	cellSize := g.ImageHeight / 2
	var images []image.Image

	for _, mf := range mediaFiles {
		var img image.Image
		var decodeErr error
		srcPath := filepath.Join(g.Root, mf)
		if isNativeImage(mf) {
			ext := strings.ToLower(filepath.Ext(mf))
			if ext == ".webp" {
				img, decodeErr = decodeWebP(srcPath)
			} else {
				img, decodeErr = decodeStdImage(srcPath)
			}
		}
		if decodeErr != nil || img == nil {
			continue
		}
		img = cropCenterSquare(img, cellSize)
		images = append(images, img)
	}

	composite := image.NewRGBA(image.Rect(0, 0, g.ImageHeight, g.ImageHeight))
	draw.Draw(composite, composite.Bounds(), image.NewUniform(color.RGBA{30, 30, 30, 255}), image.Point{}, draw.Src)

	for i, img := range images {
		x := (i % 2) * cellSize
		y := (i / 2) * cellSize
		draw.Draw(composite, image.Rect(x, y, x+cellSize, y+cellSize), img, image.Point{}, draw.Over)
	}

	if err := os.MkdirAll(filepath.Dir(thumbPath), 0755); err != nil {
		return "", err
	}
	f, err := os.Create(thumbPath)
	if err != nil {
		return "", err
	}
	defer f.Close()

	if err := webpenc.Encode(f, composite, webpenc.Options{Quality: g.Quality}); err != nil {
		return "", err
	}

	return thumbPath, nil
}
