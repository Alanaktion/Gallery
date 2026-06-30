package main

import (
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"unicode"

	_ "golang.org/x/image/bmp"
	_ "golang.org/x/image/tiff"
	"golang.org/x/image/webp"
)

type GalleryItem struct {
	Name        string  `json:"name"`
	Path        string  `json:"path"`
	IsDir       bool    `json:"isDir"`
	AspectRatio float64 `json:"aspectRatio"`
	Ext         string  `json:"ext"`
}

type Gallery struct {
	Config
	ffmpegOK bool
}

func NewGallery(cfg Config) *Gallery {
	return &Gallery{Config: cfg}
}

func (g *Gallery) ListDir(relPath string, offset, limit int) ([]GalleryItem, int, error) {
	absPath := filepath.Join(g.Root, relPath)
	entries, err := os.ReadDir(absPath)
	if err != nil {
		return nil, 0, err
	}

	var all []GalleryItem
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasPrefix(name, ".") {
			continue
		}
		all = append(all, GalleryItem{
			Name:  name,
			Path:  filepath.Join(relPath, name),
			IsDir: entry.IsDir(),
			Ext:   strings.ToLower(filepath.Ext(name)),
		})
	}

	sort.Slice(all, func(i, j int) bool {
		if all[i].IsDir != all[j].IsDir {
			return all[i].IsDir
		}
		return naturalLess(all[i].Name, all[j].Name)
	})

	total := len(all)

	if offset < 0 {
		offset = 0
	}
	if limit <= 0 {
		limit = total
	}
	end := offset + limit
	if end > total {
		end = total
	}
	if offset > total {
		offset = total
	}

	items := all[offset:end]

	for i := range items {
		if !items[i].IsDir {
			ar, err := g.aspectRatio(items[i].Path)
			if err == nil {
				items[i].AspectRatio = ar
			} else {
				items[i].AspectRatio = 1
			}
		} else {
			items[i].AspectRatio = 1
		}
	}

	return items, total, nil
}

func isMedia(path string) bool {
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp":
		return true
	case ".avif", ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg":
		return true
	}
	return false
}

func (g *Gallery) aspectRatio(relPath string) (float64, error) {
	absPath := filepath.Join(g.Root, relPath)
	f, err := os.Open(absPath)
	if err != nil {
		return 1, err
	}
	defer f.Close()

	ext := strings.ToLower(filepath.Ext(relPath))
	var cfg image.Config

	if ext == ".webp" {
		cfg, err = webp.DecodeConfig(f)
	} else {
		cfg, _, err = image.DecodeConfig(f)
	}
	if err != nil {
		return 1, err
	}

	if cfg.Height == 0 {
		return 1, fmt.Errorf("zero height")
	}
	ar := float64(cfg.Width) / float64(cfg.Height)
	if ar > g.MaxAspect {
		ar = g.MaxAspect
	}
	if ar < 0.1 {
		ar = 0.1
	}
	return ar, nil
}

func safeJoin(root, rel string) (string, error) {
	if strings.Contains(rel, "..") {
		return "", fmt.Errorf("invalid path")
	}
	abs := filepath.Join(root, rel)
	cleanRoot := filepath.Clean(root)
	if !strings.HasPrefix(abs, cleanRoot+string(os.PathSeparator)) && abs != cleanRoot {
		return "", fmt.Errorf("access denied")
	}
	return abs, nil
}

type segment struct {
	num   int
	text  string
	isNum bool
}

func naturalLess(a, b string) bool {
	segsA := splitNatural(a)
	segsB := splitNatural(b)

	for i := 0; i < len(segsA) && i < len(segsB); i++ {
		if segsA[i].isNum && segsB[i].isNum {
			if segsA[i].num != segsB[i].num {
				return segsA[i].num < segsB[i].num
			}
		} else if !segsA[i].isNum && !segsB[i].isNum {
			if segsA[i].text != segsB[i].text {
				return segsA[i].text < segsB[i].text
			}
		} else {
			return segsA[i].isNum
		}
	}
	return len(segsA) < len(segsB)
}

func splitNatural(s string) []segment {
	var segs []segment
	i := 0
	for i < len(s) {
		if unicode.IsDigit(rune(s[i])) {
			j := i
			for j < len(s) && unicode.IsDigit(rune(s[j])) {
				j++
			}
			n, _ := strconv.Atoi(s[i:j])
			segs = append(segs, segment{num: n, isNum: true})
			i = j
		} else {
			j := i
			for j < len(s) && !unicode.IsDigit(rune(s[j])) {
				j++
			}
			segs = append(segs, segment{text: s[i:j], isNum: false})
			i = j
		}
	}
	return segs
}
