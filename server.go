package main

import (
	"embed"
	"fmt"
	"html/template"
	"io/fs"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

//go:embed templates/*
var templateFS embed.FS

//go:embed static/*
var staticFS embed.FS

type PageData struct {
	Title       string
	CurrentPath string
	Breadcrumbs []Breadcrumb
	Items       []GalleryItem
	ImageHeight int
	Error       string
}

type Breadcrumb struct {
	Name string
	Path string
}

func (g *Gallery) Handler() http.Handler {
	mux := http.NewServeMux()

	staticSub, err := fs.Sub(staticFS, "static")
	if err != nil {
		log.Fatalf("static fs: %v", err)
	}
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.FS(staticSub))))

	mux.HandleFunc("GET /", g.handleRoot)
	mux.HandleFunc("GET /browse/{path...}", g.handleBrowse)
	mux.HandleFunc("GET /content/{path...}", g.handleContent)
	mux.HandleFunc("GET /thumbnail/{path...}", g.handleThumbnail)

	return mux
}

func (g *Gallery) handleRoot(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	http.Redirect(w, r, "/browse/", http.StatusFound)
}

func (g *Gallery) handleBrowse(w http.ResponseWriter, r *http.Request) {
	relPath := strings.TrimPrefix(r.URL.Path, "/browse/")
	relPath = strings.TrimSuffix(relPath, "/")

	if _, err := safeJoin(g.Root, relPath); err != nil {
		http.Error(w, "access denied", http.StatusForbidden)
		return
	}

	absPath := filepath.Join(g.Root, relPath)
	info, err := os.Stat(absPath)
	if err != nil {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	if !info.IsDir() {
		http.Error(w, "not a directory", http.StatusBadRequest)
		return
	}

	items, err := g.ListDir(relPath)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	tmpl, err := template.ParseFS(templateFS, "templates/gallery.html")
	if err != nil {
		http.Error(w, fmt.Sprintf("template error: %v", err), http.StatusInternalServerError)
		return
	}

	data := PageData{
		Title:       g.Title,
		CurrentPath: relPath,
		Breadcrumbs: buildBreadcrumbs(relPath),
		Items:       items,
		ImageHeight: g.ImageHeight,
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := tmpl.Execute(w, data); err != nil {
		log.Printf("template execute: %v", err)
	}
}

func (g *Gallery) handleContent(w http.ResponseWriter, r *http.Request) {
	relPath := strings.TrimPrefix(r.URL.Path, "/content/")

	absPath, err := safeJoin(g.Root, relPath)
	if err != nil {
		http.Error(w, "access denied", http.StatusForbidden)
		return
	}

	info, err := os.Stat(absPath)
	if err != nil {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	if info.IsDir() {
		http.Error(w, "cannot browse directory", http.StatusBadRequest)
		return
	}

	if !isMedia(relPath) {
		http.Error(w, "unsupported media type", http.StatusBadRequest)
		return
	}

	cType := mimeType(filepath.Ext(relPath))
	w.Header().Set("Content-Type", cType)
	http.ServeFile(w, r, absPath)
}

func (g *Gallery) handleThumbnail(w http.ResponseWriter, r *http.Request) {
	relPath := strings.TrimPrefix(r.URL.Path, "/thumbnail/")

	absPath, err := safeJoin(g.Root, relPath)
	if err != nil {
		http.Error(w, "access denied", http.StatusForbidden)
		return
	}

	if _, err := os.Stat(absPath); err != nil {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}

	var thumbPath string

	if isNativeImage(relPath) {
		thumbPath, err = g.GenerateThumbnail(relPath)
	} else if isFFmpegFormat(relPath) {
		thumbPath, err = g.GenerateFFmpegThumbnail(relPath)
	} else {
		http.Error(w, "unsupported format", http.StatusBadRequest)
		return
	}

	if err != nil {
		if err == os.ErrNotExist && isFFmpegFormat(relPath) && !g.ffmpegOK {
			http.Error(w, "ffmpeg not available", http.StatusInternalServerError)
			return
		}
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "image/webp")
	w.Header().Set("Cache-Control", "public, max-age=86400")
	http.ServeFile(w, r, thumbPath)
}

func buildBreadcrumbs(relPath string) []Breadcrumb {
	if relPath == "" {
		return nil
	}
	parts := strings.Split(relPath, string(os.PathSeparator))
	crumbs := make([]Breadcrumb, 0, len(parts))
	var cur string
	for _, p := range parts {
		if p == "" {
			continue
		}
		cur = filepath.Join(cur, p)
		crumbs = append(crumbs, Breadcrumb{Name: p, Path: cur})
	}
	return crumbs
}

func mimeType(ext string) string {
	switch strings.ToLower(ext) {
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".png":
		return "image/png"
	case ".gif":
		return "image/gif"
	case ".webp":
		return "image/webp"
	case ".avif":
		return "image/avif"
	case ".bmp":
		return "image/bmp"
	case ".tiff", ".tif":
		return "image/tiff"
	case ".mp4":
		return "video/mp4"
	case ".webm":
		return "video/webm"
	case ".mov":
		return "video/quicktime"
	case ".avi":
		return "video/x-msvideo"
	case ".mkv":
		return "video/x-matroska"
	default:
		return "application/octet-stream"
	}
}
