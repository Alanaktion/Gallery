package main

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Root        string
	Port        string
	ImageHeight int
	MaxAspect   float64
	CacheDir    string
	Title       string
	Quality     int
	PageSize    int
	// FileExts lists non-media extensions shown as downloadable file
	// tiles (e.g. .txt, .zip). Empty disables the feature.
	FileExts []string
}

var defaultFileExts = []string{
	// archives
	".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz",
	// documents
	".pdf", ".txt", ".md", ".doc", ".docx", ".odt", ".rtf", ".epub",
	// data & subtitle/text files
	".csv", ".json", ".xml", ".gpx", ".log", ".nfo", ".srt", ".vtt", ".yaml", ".yml",
}

func LoadConfig() Config {
	return Config{
		Root:        envStr("GALLERY_ROOT", "/files"),
		Port:        envStr("GALLERY_PORT", "8080"),
		ImageHeight: envInt("GALLERY_IMAGE_HEIGHT", 250),
		MaxAspect:   envFloat("GALLERY_MAX_ASPECT", 2.0),
		CacheDir:    envStr("GALLERY_CACHE_DIR", "/tmp/gallery-cache"),
		Title:       envStr("GALLERY_TITLE", "Gallery"),
		Quality:     envInt("GALLERY_QUALITY", 85),
		PageSize:    envInt("GALLERY_PAGE_SIZE", 200),
		FileExts:    envExtList("GALLERY_FILE_EXTS", defaultFileExts),
	}
}

func envStr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envFloat(key string, def float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}

// envExtList parses a comma-separated extension list like ".txt, .zip".
// Unset returns the default; set-but-empty disables the list entirely.
func envExtList(key string, def []string) []string {
	v, ok := os.LookupEnv(key)
	if !ok {
		return def
	}
	var out []string
	seen := map[string]bool{}
	for _, e := range strings.Split(v, ",") {
		e = strings.ToLower(strings.TrimSpace(e))
		if e == "" {
			continue
		}
		if !strings.HasPrefix(e, ".") {
			e = "." + e
		}
		if !seen[e] {
			seen[e] = true
			out = append(out, e)
		}
	}
	return out
}
