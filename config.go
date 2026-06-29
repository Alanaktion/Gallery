package main

import (
	"os"
	"strconv"
)

type Config struct {
	Root        string
	Port        string
	ImageHeight int
	MaxAspect   float64
	CacheDir    string
	Title       string
	Quality     int
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
