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
	"strings"

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
	// FileKind is set for listed non-media files (archive, text, doc,
	// data, file) so the UI can render them as file tiles.
	FileKind string `json:"fileKind"`
}

type Gallery struct {
	Config
	ffmpegOK  bool
	extraExts map[string]bool
}

func NewGallery(cfg Config) *Gallery {
	extra := make(map[string]bool, len(cfg.FileExts))
	for _, e := range cfg.FileExts {
		extra[e] = true
	}
	return &Gallery{Config: cfg, extraExts: extra}
}

// isExtraFile reports whether name is a configured non-media file to list.
func (g *Gallery) isExtraFile(name string) bool {
	ext := strings.ToLower(filepath.Ext(name))
	return g.extraExts[ext]
}

// fileKind maps a non-media extension to an icon category.
func fileKind(ext string) string {
	switch ext {
	case ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz":
		return "archive"
	case ".txt", ".md", ".markdown", ".log", ".nfo", ".srt", ".vtt", ".sub":
		return "text"
	case ".pdf", ".doc", ".docx", ".odt", ".rtf", ".epub":
		return "doc"
	case ".csv", ".tsv", ".json", ".xml", ".gpx", ".kml", ".yaml", ".yml", ".toml":
		return "data"
	default:
		return "file"
	}
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
		if !entry.IsDir() && !isMedia(name) && !g.isExtraFile(name) {
			continue
		}
		item := GalleryItem{
			Name:  name,
			Path:  filepath.Join(relPath, name),
			IsDir: entry.IsDir(),
			Ext:   strings.ToLower(filepath.Ext(name)),
		}
		if !entry.IsDir() && !isMedia(name) {
			item.FileKind = fileKind(item.Ext)
		}
		all = append(all, item)
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
		if items[i].IsDir || items[i].FileKind != "" {
			items[i].AspectRatio = 1
			continue
		}
		ar, err := g.aspectRatio(items[i].Path)
		if err == nil {
			items[i].AspectRatio = ar
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
	case ".avif", ".heic", ".heif", ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg":
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

type natSegment struct {
	isNum bool
	// key is the comparison key: lowercased text for text segments, or
	// the digit run with leading zeros stripped for numeric segments.
	key string
	// raw is the original segment text, used as a deterministic tie-break.
	raw string
}

// naturalLess orders names the way humans expect: case-insensitively,
// with digit runs compared by numeric value, so "asdf1" sorts before
// "Asdf02" and "img2" before "img10".
func naturalLess(a, b string) bool {
	segsA := splitNatural(a)
	segsB := splitNatural(b)

	for i := 0; i < len(segsA) && i < len(segsB); i++ {
		if c := cmpNatSeg(segsA[i], segsB[i]); c != 0 {
			return c < 0
		}
	}
	if len(segsA) != len(segsB) {
		return len(segsA) < len(segsB)
	}
	// Deterministic tie-break on original case for names that are
	// equal case-insensitively (e.g. "A.png" before "a.png").
	for i := range segsA {
		if segsA[i].raw != segsB[i].raw {
			return segsA[i].raw < segsB[i].raw
		}
	}
	return false
}

// cmpNatSeg compares two segments by key only: numeric segments by value
// (longer digit run wins; equal lengths compare lexicographically, so
// there is no Atoi overflow), text segments case-insensitively.
func cmpNatSeg(sa, sb natSegment) int {
	switch {
	case sa.isNum && sb.isNum:
		if len(sa.key) != len(sb.key) {
			if len(sa.key) < len(sb.key) {
				return -1
			}
			return 1
		}
		return strings.Compare(sa.key, sb.key)
	case !sa.isNum && !sb.isNum:
		return strings.Compare(sa.key, sb.key)
	case sa.isNum:
		return -1
	default:
		return 1
	}
}

func splitNatural(s string) []natSegment {
	var segs []natSegment
	i := 0
	for i < len(s) {
		j := i
		if s[i] >= '0' && s[i] <= '9' {
			for j < len(s) && s[j] >= '0' && s[j] <= '9' {
				j++
			}
			raw := s[i:j]
			segs = append(segs, natSegment{isNum: true, key: strings.TrimLeft(raw, "0"), raw: raw})
		} else {
			for j < len(s) && (s[j] < '0' || s[j] > '9') {
				j++
			}
			raw := s[i:j]
			segs = append(segs, natSegment{key: strings.ToLower(raw), raw: raw})
		}
		i = j
	}
	return segs
}
