package main

import (
	"bufio"
	"bytes"
	"io/fs"
	"log"
	"os/exec"
	"path/filepath"
	"strings"
)

var hasRclip bool

func checkRclip() bool {
	if _, err := exec.LookPath("rclip"); err == nil {
		return true
	}
	return false
}

func indexRclip(root string) {
	cmd := exec.Command("rclip", "index", root)
	if err := cmd.Run(); err != nil {
		log.Printf("rclip index: %v", err)
	}
}

func (g *Gallery) Search(query string) ([]GalleryItem, error) {
	if hasRclip {
		return g.rclipSearch(query)
	}
	return g.filenameSearch(query)
}

func (g *Gallery) filenameSearch(query string) ([]GalleryItem, error) {
	q := strings.ToLower(query)
	var results []GalleryItem

	err := filepath.WalkDir(g.Root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() || strings.HasPrefix(d.Name(), ".") {
			return nil
		}
		media := isMedia(path)
		if !media && !g.isExtraFile(path) {
			return nil
		}
		if strings.Contains(strings.ToLower(d.Name()), q) {
			relPath, err := filepath.Rel(g.Root, path)
			if err != nil {
				return nil
			}
			if _, err := safeJoin(g.Root, relPath); err != nil {
				return nil
			}
			item := GalleryItem{
				Name:  d.Name(),
				Path:  filepath.ToSlash(relPath),
				IsDir: false,
				Ext:   strings.ToLower(filepath.Ext(d.Name())),
			}
			if !media {
				item.FileKind = fileKind(item.Ext)
				item.AspectRatio = 1
			} else {
				ar, err := g.aspectRatio(item.Path)
				if err == nil {
					item.AspectRatio = ar
				} else {
					item.AspectRatio = 1
				}
			}
			results = append(results, item)
		}
		return nil
	})

	return results, err
}

func (g *Gallery) rclipSearch(query string) ([]GalleryItem, error) {
	cmd := exec.Command("rclip", "search", query, "-t", "200")
	output, err := cmd.Output()
	if err != nil {
		log.Printf("rclip search: %v, falling back to filename search", err)
		return g.filenameSearch(query)
	}

	var items []GalleryItem
	scanner := bufio.NewScanner(bytes.NewReader(output))
	first := true
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if first {
			first = false
			continue
		}
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "\t", 2)
		if len(parts) < 2 {
			continue
		}
		filePath := strings.Trim(parts[1], `"`)
		if filePath == "" {
			continue
		}
		relPath, err := filepath.Rel(g.Root, filePath)
		if err != nil {
			continue
		}
		if _, err := safeJoin(g.Root, relPath); err != nil {
			continue
		}
		item := GalleryItem{
			Name:  filepath.Base(filePath),
			Path:  filepath.ToSlash(relPath),
			IsDir: false,
			Ext:   strings.ToLower(filepath.Ext(filePath)),
		}
		ar, err := g.aspectRatio(item.Path)
		if err == nil {
			item.AspectRatio = ar
		} else {
			item.AspectRatio = 1
		}
		items = append(items, item)
	}

	if len(items) == 0 {
		return g.filenameSearch(query)
	}
	return items, nil
}
