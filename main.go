package main

import (
	"log"
	"net/http"
)

func main() {
	cfg := LoadConfig()

	log.Printf("root: %s", cfg.Root)
	log.Printf("port: %s", cfg.Port)
	log.Printf("image height: %dpx", cfg.ImageHeight)
	log.Printf("max aspect: %.1f", cfg.MaxAspect)
	log.Printf("cache dir: %s", cfg.CacheDir)

	g := NewGallery(cfg)
	g.ffmpegOK = checkFFmpeg()
	if g.ffmpegOK {
		log.Println("ffmpeg: available")
	} else {
		log.Println("ffmpeg: not found (AVIF/video thumbnails disabled)")
	}

	handler := g.Handler()

	addr := ":" + cfg.Port
	log.Printf("listening on %s", addr)
	if err := http.ListenAndServe(addr, handler); err != nil {
		log.Fatalf("server: %v", err)
	}
}
