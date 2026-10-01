package main

import (
	"embed"
	"encoding/json"
	"fmt"
	"html/template"
	"io/fs"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
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
	PageSize    int
	HasMore     bool
	Error       string
	SearchQuery string
	IsSearch    bool
}

type browseResponse struct {
	Items   []GalleryItem `json:"items"`
	Total   int           `json:"total"`
	HasMore bool          `json:"hasMore"`
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
	mux.HandleFunc("GET /search", g.handleSearch)

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

	page := 1
	if p := r.URL.Query().Get("page"); p != "" {
		if n, err := strconv.Atoi(p); err == nil && n > 1 {
			page = n
		}
	}

	pageSize := g.PageSize
	if pageSize <= 0 {
		pageSize = 200
	}
	offset := (page - 1) * pageSize

	items, total, err := g.ListDir(relPath, offset, pageSize)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	hasMore := offset+pageSize < total

	if page > 1 {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(browseResponse{
			Items:   items,
			Total:   total,
			HasMore: hasMore,
		})
		return
	}

	tmpl, err := galleryTemplate()
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
		PageSize:    pageSize,
		HasMore:     hasMore,
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

	if !isMedia(relPath) && !g.isExtraFile(relPath) {
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

	info, err := os.Stat(absPath)
	if err != nil {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}

	var thumbPath string

	if info.IsDir() {
		thumbPath, err = g.GenerateFolderThumbnail(relPath)
	} else if isFFmpegFormat(relPath) && (!isNativeImage(relPath) || g.ffmpegOK) {
		if isNativeImage(relPath) {
			thumbPath, err = g.GenerateThumbnail(relPath)
			if err != nil && g.ffmpegOK {
				thumbPath, err = g.GenerateFFmpegThumbnail(relPath)
			}
		} else {
			thumbPath, err = g.GenerateFFmpegThumbnail(relPath)
		}
	} else if isNativeImage(relPath) {
		thumbPath, err = g.GenerateThumbnail(relPath)
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
	// Thumbnail URLs are unversioned and the cached file is regenerated when
	// the source changes, so allow only a short freshness window and then
	// revalidate cheaply via ETag/Last-Modified (http.ServeFile answers 304).
	if st, err := os.Stat(thumbPath); err == nil {
		w.Header().Set("ETag", fmt.Sprintf(`"%x-%x"`, st.ModTime().UnixNano(), st.Size()))
	}
	w.Header().Set("Cache-Control", "public, max-age=3600, stale-while-revalidate=86400")
	http.ServeFile(w, r, thumbPath)
}

// galleryTemplate parses the gallery page template with its helper funcs.
// The root name must match the file's base name so Execute renders it.
func galleryTemplate() (*template.Template, error) {
	return template.New("gallery.html").Funcs(template.FuncMap{
		"extLabel": extLabel,
	}).ParseFS(templateFS, "templates/gallery.html")
}

// extLabel renders an extension like ".zip" as "ZIP" for file tiles.
func extLabel(ext string) string {
	return strings.ToUpper(strings.TrimPrefix(ext, "."))
}

// mustJSON marshals a string to a JSON string literal for embedding in JS.
func mustJSON(s string) string {
	b, err := json.Marshal(s)
	if err != nil {
		return `""`
	}
	return string(b)
}

// CurrentPathJS renders CurrentPath as a JS string literal for the
// infinite-scroll script. html/template would otherwise escape the
// quotes produced by printf "%q", corrupting the fetch URL.
func (p PageData) CurrentPathJS() template.JS {
	return template.JS(mustJSON(p.CurrentPath))
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

func (g *Gallery) handleSearch(w http.ResponseWriter, r *http.Request) {
	query := strings.TrimSpace(r.URL.Query().Get("q"))
	if query == "" {
		http.Error(w, "missing search query", http.StatusBadRequest)
		return
	}

	results, err := g.Search(query)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	tmpl, err := galleryTemplate()
	if err != nil {
		http.Error(w, fmt.Sprintf("template error: %v", err), http.StatusInternalServerError)
		return
	}

	data := PageData{
		Title:       g.Title + " - Search",
		CurrentPath: "",
		Items:       results,
		ImageHeight: g.ImageHeight,
		PageSize:    len(results),
		SearchQuery: query,
		IsSearch:    true,
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := tmpl.Execute(w, data); err != nil {
		log.Printf("template execute: %v", err)
	}
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
	case ".heic", ".heif":
		return "image/heic"
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
	case ".svg":
		return "image/svg+xml"
	case ".txt":
		return "text/plain; charset=utf-8"
	case ".md", ".markdown":
		return "text/markdown; charset=utf-8"
	case ".csv", ".tsv":
		return "text/csv; charset=utf-8"
	case ".json":
		return "application/json"
	case ".xml", ".gpx", ".kml":
		return "application/xml"
	case ".pdf":
		return "application/pdf"
	case ".zip":
		return "application/zip"
	case ".rar":
		return "application/vnd.rar"
	case ".7z":
		return "application/x-7z-compressed"
	case ".tar":
		return "application/x-tar"
	case ".gz", ".tgz":
		return "application/gzip"
	case ".bz2":
		return "application/x-bzip2"
	case ".xz":
		return "application/x-xz"
	case ".doc":
		return "application/msword"
	case ".docx":
		return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	case ".odt":
		return "application/vnd.oasis.opendocument.text"
	case ".rtf":
		return "application/rtf"
	case ".epub":
		return "application/epub+zip"
	case ".yaml", ".yml":
		return "application/yaml"
	case ".vtt":
		return "text/vtt; charset=utf-8"
	case ".srt", ".sub":
		return "application/x-subrip"
	default:
		return "application/octet-stream"
	}
}
