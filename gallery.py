#!/usr/bin/env python3
"""Lightweight image gallery server."""

import argparse
import json
import mimetypes
import re
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif',
              '.webp', '.bmp', '.tiff', '.tif', '.avif'}
VIDEO_EXTS = {'.mp4', '.webm', '.ogv', '.ogg', '.mov', '.m4v', '.mkv', '.avi'}
ALL_MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

ROOT: Path = Path('.')  # resolved absolute path, set in main()


def natural_key(s: str) -> list:
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def media_type(name: str) -> str:
    return 'video' if Path(name).suffix.lower() in VIDEO_EXTS else 'image'


def validate_rel_path(s: str) -> bool:
    """Return True if s is a safe relative path (no traversal, no backslash)."""
    if not isinstance(s, str):
        return False
    if s == '':
        return True
    if '\\' in s:
        return False
    for part in s.split('/'):
        if part in ('', '.', '..'):
            return False
    return True


def resolve_safe(rel: str) -> Path | None:
    """Resolve rel within ROOT. Returns absolute Path or None if unsafe."""
    try:
        p = (ROOT / rel).resolve()
        p.relative_to(ROOT)  # raises ValueError if outside ROOT
        return p
    except (ValueError, OSError):
        return None


def unique_dest(dest_dir: Path, name: str) -> Path:
    """Return a unique path in dest_dir for name, adding _1, _2, … suffixes."""
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while True:
        dest = dest_dir / f'{stem}_{i}{suffix}'
        if not dest.exists():
            return dest
        i += 1


def safe_dest_dir(parent: Path, name: str) -> Path | None:
    """
    Return an existing-or-creatable directory at parent/name.
    Returns None if a non-directory or symlink already exists there.
    """
    d = parent / name
    if d.is_symlink():
        return None
    if d.exists() and not d.is_dir():
        return None
    d.mkdir(exist_ok=True)
    try:
        d.resolve().relative_to(ROOT)
    except ValueError:
        return None
    return d


# ---------------------------------------------------------------------------
# Embedded single-page application
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Review</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #111;
      color: #e0e0e0;
      font-family: system-ui, -apple-system, sans-serif;
      min-height: 100vh;
    }

    /* ── Browse view ─────────────────────────────────────────── */
    #browse { padding: 1rem; }

    .toolbar {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 1rem;
      flex-wrap: wrap;
    }
    .breadcrumb {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.9rem;
      flex: 1;
      min-width: 0;
    }
    .crumb {
      cursor: pointer;
      color: #7ab8f5;
      white-space: nowrap;
      text-decoration: none;
      /* button/link reset */
      appearance: none;
      -webkit-appearance: none;
      background: none;
      border: none;
      padding: 0;
      font: inherit;
    }
    .crumb:hover { text-decoration: underline; }
    .crumb-sep { color: #444; }

    .view-btns { display: flex; gap: 0.25rem; flex-shrink: 0; }
    .view-btn {
      background: #2a2a2a;
      border: 1px solid #3a3a3a;
      color: #aaa;
      padding: 0.35rem 0.6rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 1rem;
      line-height: 1;
      transition: background 0.1s, color 0.1s;
    }
    .view-btn:hover { background: #333; color: #fff; }
    .view-btn.active { background: #1a3a5a; border-color: #4a8fc4; color: #7ab8f5; }

    /* ── Grid view ───────────────────────────────────────────── */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 0.75rem;
    }
    .item {
      cursor: pointer;
      border-radius: 6px;
      overflow: hidden;
      background: #1e1e1e;
      transition: transform 0.1s, box-shadow 0.1s;
      display: block;
      text-decoration: none;
      color: inherit;
      /* button/link reset */
      appearance: none;
      -webkit-appearance: none;
      border: none;
      padding: 0;
      font: inherit;
      text-align: inherit;
      width: 100%;
    }
    .item:hover { transform: scale(1.03); box-shadow: 0 4px 16px rgba(0,0,0,0.5); }
    .item-thumb {
      width: 100%;
      aspect-ratio: 1;
      object-fit: cover;
      display: block;
      background: #2a2a2a;
    }
    .item-icon {
      width: 100%;
      aspect-ratio: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 3rem;
      background: #1e1e1e;
    }
    .item-icon.video-icon {
      background: #1a1a2e;
      font-size: 2.5rem;
      flex-direction: column;
      gap: 0.25rem;
    }
    .video-badge {
      font-size: 0.65rem;
      color: #8888cc;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .item-label {
      padding: 0.35rem 0.5rem;
      font-size: 0.72rem;
      text-align: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: #bbb;
    }

    /* ── List view ───────────────────────────────────────────── */
    .list-view {
      list-style: none;
      border: 1px solid #2a2a2a;
      border-radius: 6px;
      overflow: hidden;
    }
    .list-item { border-bottom: 1px solid #1e1e1e; }
    .list-item:last-child { border-bottom: none; }
    /* Full-width button inside each list row */
    .list-btn {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.45rem 0.75rem;
      width: 100%;
      cursor: pointer;
      font: inherit;
      font-size: 0.88rem;
      background: none;
      border: none;
      color: inherit;
      text-align: left;
      text-decoration: none;
      transition: background 0.1s;
      user-select: none;
    }
    .list-btn:hover { background: #1e1e1e; }
    .list-icon { font-size: 1rem; flex-shrink: 0; }
    .list-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #ddd; }

    .empty {
      color: #555;
      text-align: center;
      margin-top: 4rem;
      font-size: 1.1rem;
    }

    /* ── Fullscreen viewer ───────────────────────────────────── */
    #fullscreen {
      display: none;
      position: fixed;
      inset: 0;
      background: #000;
      z-index: 100;
      user-select: none;
    }

    #fs-img, #fs-vid {
      width: 100%;
      height: 100vh;
      object-fit: scale-down;
      display: block;
    }
    #fs-vid { background: #000; }

    .nav-btn {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      background: rgba(255,255,255,0.08);
      border: none;
      color: #fff;
      font-size: 2.5rem;
      width: 3rem;
      height: 6rem;
      cursor: pointer;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.15s, opacity 0.3s;
      line-height: 1;
    }
    .nav-btn:hover:not(:disabled) { background: rgba(255,255,255,0.22); }
    .nav-btn:disabled { opacity: 0.12; cursor: default; }
    #btn-prev { left: 0.5rem; }
    #btn-next { right: 0.5rem; }

    /* Controls hidden when keyboard is driving */
    #fullscreen.controls-hidden .nav-btn { opacity: 0; pointer-events: none; }
    #fullscreen.controls-hidden .fs-bar  { opacity: 0; pointer-events: none; }

    .fs-bar {
      position: absolute;
      top: 0; left: 0; right: 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.75rem 1rem;
      background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent);
      pointer-events: none;
      transition: opacity 0.3s;
    }
    .fs-bar > * { pointer-events: auto; }

    .fs-info { display: flex; flex-direction: column; gap: 0.15rem; overflow: hidden; }
    #fs-name {
      font-size: 0.85rem;
      color: #ddd;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 50vw;
    }
    #fs-counter { font-size: 0.72rem; color: #888; }

    .fs-actions { display: flex; gap: 0.5rem; flex-shrink: 0; }
    .act-btn {
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.15);
      color: #fff;
      padding: 0.4rem 0.85rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 1.5rem;
      transition: background 0.15s;
      white-space: nowrap;
      line-height: 1;
    }
    .act-btn:hover { background: rgba(255,255,255,0.22); }
    .act-btn.active { background: rgba(255,255,255,0.18); border-color: rgba(255,255,255,0.35); }
    #btn-fav { color: #ffd700; }
    #btn-fav:hover { background: rgba(255,215,0,0.18); }
    #btn-del { color: #ff6b6b; }
    #btn-del:hover { background: rgba(255,107,107,0.18); }

    .danger-btn {
      background: #2a1a1a;
      border: 1px solid #5a2a2a;
      color: #ff8888;
      padding: 0.35rem 0.7rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.8rem;
      line-height: 1;
      transition: background 0.1s, color 0.1s;
      white-space: nowrap;
      /* button reset */
      appearance: none;
      -webkit-appearance: none;
    }
    .danger-btn:hover { background: #3a1a1a; color: #ffaaaa; }

    .toast {
      position: fixed;
      bottom: 1.5rem;
      left: 50%;
      transform: translateX(-50%);
      background: #2a2a2a30;
      color: #fff;
      padding: 0.5rem 1.5rem;
      border-radius: 20px;
      font-size: 0.9rem;
      z-index: 9999;
      pointer-events: none;
      animation: toastfade 2.2s ease forwards;
    }
    @keyframes toastfade {
      0%, 65% { opacity: 1; }
      100% { opacity: 0; }
    }

    /* ── Loading indicator ───────────────────────────────────── */
    .loading {
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 4rem;
    }
    .spinner {
      width: 2rem;
      height: 2rem;
      border: 3px solid #2a2a2a;
      border-top-color: #7ab8f5;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>

<div id="browse">
  <div class="toolbar">
    <nav class="breadcrumb" id="breadcrumb" aria-label="Directory path"></nav>
    <button class="danger-btn" id="btn-empty-trash" style="display:none" title="Permanently delete all files in the trash folder">🗑 Empty Trash</button>
    <button class="danger-btn" id="btn-empty-nonfavs" style="display:none" title="Permanently delete all files in this folder that are not in fav">✂ Keep Favs Only</button>
    <button class="danger-btn" id="btn-delete-dir" style="display:none" title="Permanently delete this entire directory and navigate up">🗑 Delete Directory</button>
    <div class="view-btns">
      <button class="view-btn" id="btn-grid-view" title="Grid view" aria-label="Grid view">⊞</button>
      <button class="view-btn" id="btn-list-view" title="List view" aria-label="List view">≡</button>
    </div>
  </div>
  <div id="media-container"></div>
</div>

<div id="fullscreen" role="dialog" aria-modal="true">
  <img id="fs-img" src="" alt="" style="display:none">
  <video id="fs-vid" autoplay controls style="display:none"></video>
  <button class="nav-btn" id="btn-prev" aria-label="Previous">&#8249;</button>
  <button class="nav-btn" id="btn-next" aria-label="Next">&#8250;</button>
  <div class="fs-bar">
    <div class="fs-info">
      <span id="fs-name"></span>
      <span id="fs-counter"></span>
    </div>
    <div class="fs-actions">
      <button class="act-btn" id="btn-fit">⊡</button>
      <button class="act-btn" id="btn-fav">★</button>
      <button class="act-btn" id="btn-del">🗑</button>
      <button class="act-btn" id="btn-close">✕</button>
    </div>
  </div>
</div>

<script>
  'use strict';

  let dirPath = '';       // current directory (relative from root, no leading/trailing slash)
  let dirMedia = [];      // [{name, type}] in current directory
  let mediaIdx = 0;       // index of current fullscreen item
  let navToken = 0;       // guards against stale navigate() responses
  let browseModified = false;  // true when a fav/delete happened in fullscreen
  let savedScrollY = 0;

  // Persist view mode and fit mode
  let viewMode = localStorage.getItem('galleryView') || 'grid';
  let fitMode  = localStorage.getItem('galleryFit')  || 'scale-down';

  // ── Path helpers ────────────────────────────────────────────

  function joinPath(a, b) {
    if (!a) return b;
    if (!b) return a;
    return a + '/' + b;
  }

  function encPath(p) {
    return p.split('/').map(encodeURIComponent).join('/');
  }

  // ── View toggle ─────────────────────────────────────────────

  function setViewMode(mode) {
    viewMode = mode;
    localStorage.setItem('galleryView', mode);
    document.getElementById('btn-grid-view').classList.toggle('active', mode === 'grid');
    document.getElementById('btn-list-view').classList.toggle('active', mode === 'list');
  }

  document.getElementById('btn-grid-view').addEventListener('click', () => {
    if (viewMode !== 'grid') { setViewMode('grid'); renderMedia(lastData); }
  });
  document.getElementById('btn-list-view').addEventListener('click', () => {
    if (viewMode !== 'list') { setViewMode('list'); renderMedia(lastData); }
  });

  // ── Fit-mode toggle ──────────────────────────────────────────

  function applyFitMode() {
    document.getElementById('fs-img').style.objectFit = fitMode;
    document.getElementById('fs-vid').style.objectFit = fitMode;
    document.getElementById('btn-fit').classList.toggle('active', fitMode === 'contain');
  }

  function toggleFitMode() {
    fitMode = fitMode === 'scale-down' ? 'contain' : 'scale-down';
    localStorage.setItem('galleryFit', fitMode);
    applyFitMode();
  }

  document.getElementById('btn-fit').addEventListener('click', toggleFitMode);

  applyFitMode();

  // ── Directory navigation ─────────────────────────────────────

  let lastData = null;

  async function navigate(path, historyMode = 'push') {
    dirPath = path;
    const token = ++navToken;

    // Update browser history
    const url = path ? '/?path=' + encodeURIComponent(path) : '/';
    if (historyMode === 'push') history.pushState({ path }, '', url);
    else if (historyMode === 'replace') history.replaceState({ path }, '', url);

    // Show loading indicator immediately
    const container = document.getElementById('media-container');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    let data;
    try {
      const res = await fetch('/api/list?path=' + encodeURIComponent(path));
      if (!res.ok) { showToast('Could not load directory'); container.textContent = ''; return; }
      data = await res.json();
    } catch { showToast('Network error'); container.textContent = ''; return; }
    if (token !== navToken) return;  // stale

    dirMedia = data.media;
    lastData = data;
    renderBreadcrumb();
    renderMedia(data);
    document.getElementById('btn-empty-trash').style.display = data.has_trash ? '' : 'none';
    const showEmptyNonFavs = data.has_fav && data.media.length;
    document.getElementById('btn-empty-nonfavs').style.display = showEmptyNonFavs ? '' : 'none';
    const showDeleteDir = dirPath !== '' && !data.has_trash && !data.has_fav && !data.dirs.length;
    document.getElementById('btn-delete-dir').style.display = showDeleteDir ? '' : 'none';
  }

  function renderBreadcrumb() {
    const bc = document.getElementById('breadcrumb');
    bc.textContent = '';

    const home = document.createElement('a');
    home.className = 'crumb';
    home.href = '/';
    home.textContent = '🏠 Home';
    home.addEventListener('click', e => {
      if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        e.preventDefault();
        navigate('');
      }
    });
    bc.appendChild(home);

    const parts = dirPath.split('/').filter(Boolean);
    let cum = '';
    for (const p of parts) {
      const sep = document.createElement('span');
      sep.className = 'crumb-sep';
      sep.textContent = ' / ';
      bc.appendChild(sep);

      cum = cum ? cum + '/' + p : p;
      const crumb = document.createElement('a');
      crumb.className = 'crumb';
      crumb.href = '/?path=' + encodeURIComponent(cum);
      crumb.textContent = p;
      const target = cum;
      crumb.addEventListener('click', e => {
        if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
          e.preventDefault();
          navigate(target);
        }
      });
      bc.appendChild(crumb);
    }
  }

  function renderMedia(data) {
    const container = document.getElementById('media-container');
    container.textContent = '';
    if (!data) return;

    if (!data.dirs.length && !data.media.length) {
      const p = document.createElement('p');
      p.className = 'empty';
      p.textContent = 'No media or folders here.';
      container.appendChild(p);
      return;
    }

    if (viewMode === 'list') {
      renderList(data, container);
    } else {
      renderGrid(data, container);
    }
  }

  function renderGrid(data, container) {
    const grid = document.createElement('div');
    grid.className = 'grid';

    const favDirsSet = new Set(data.fav_dirs || []);
    for (const d of data.dirs) {
      const target = joinPath(dirPath, d);
      const item = makeGridFolder(d, favDirsSet.has(d), target);
      item.addEventListener('click', e => {
        if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
          e.preventDefault();
          navigate(target);
        }
      });
      grid.appendChild(item);
    }

    for (let i = 0; i < data.media.length; i++) {
      const {name, type} = data.media[i];
      const item = type === 'video' ? makeGridVideo(name) : makeGridImage(name, i);
      if (type === 'image') {
        // img src set inside makeGridImage
      }
      const idx = i;
      item.addEventListener('click', () => openFS(idx));
      grid.appendChild(item);
    }

    container.appendChild(grid);
  }

  function makeGridFolder(name, hasFav, targetPath) {
    const item = document.createElement('a');
    item.className = 'item';
    item.href = targetPath ? '/?path=' + encodeURIComponent(targetPath) : '/';

    const icon = document.createElement('div');
    icon.className = 'item-icon';
    icon.textContent = '📁';

    const label = document.createElement('div');
    label.className = 'item-label';
    label.textContent = hasFav ? name + ' ♥' : name;

    item.appendChild(icon);
    item.appendChild(label);
    return item;
  }

  function makeGridImage(name, idx) {
    const item = document.createElement('button');
    item.className = 'item';
    item.type = 'button';

    const thumb = document.createElement('img');
    thumb.className = 'item-thumb';
    thumb.src = '/files/' + encPath(joinPath(dirPath, name));
    thumb.loading = 'lazy';
    thumb.alt = name;

    const label = document.createElement('div');
    label.className = 'item-label';
    label.textContent = name;

    item.appendChild(thumb);
    item.appendChild(label);
    return item;
  }

  function makeGridVideo(name) {
    const item = document.createElement('button');
    item.className = 'item';
    item.type = 'button';

    const icon = document.createElement('div');
    icon.className = 'item-icon video-icon';

    const play = document.createElement('span');
    play.textContent = '▶';

    const badge = document.createElement('span');
    badge.className = 'video-badge';
    badge.textContent = name.split('.').pop().toUpperCase();

    icon.appendChild(play);
    icon.appendChild(badge);

    const label = document.createElement('div');
    label.className = 'item-label';
    label.textContent = name;

    item.appendChild(icon);
    item.appendChild(label);
    return item;
  }

  function renderList(data, container) {
    const frag = document.createDocumentFragment();
    const ul = document.createElement('ul');
    ul.className = 'list-view';

    const favDirsSet = new Set(data.fav_dirs || []);
    for (const d of data.dirs) {
      const li = document.createElement('li');
      li.className = 'list-item';

      const target = joinPath(dirPath, d);
      const btn = document.createElement('a');
      btn.className = 'list-btn';
      btn.href = target ? '/?path=' + encodeURIComponent(target) : '/';

      const icon = document.createElement('span');
      icon.className = 'list-icon';
      icon.textContent = favDirsSet.has(d) ? '💌' : '📁';

      const nm = document.createElement('span');
      nm.className = 'list-name';
      nm.textContent = d;

      btn.appendChild(icon);
      btn.appendChild(nm);
      btn.addEventListener('click', e => {
        if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
          e.preventDefault();
          navigate(target);
        }
      });
      li.appendChild(btn);
      ul.appendChild(li);
    }

    for (let i = 0; i < data.media.length; i++) {
      const {name, type} = data.media[i];
      const li = document.createElement('li');
      li.className = 'list-item';

      const btn = document.createElement('button');
      btn.className = 'list-btn';
      btn.type = 'button';

      const icon = document.createElement('span');
      icon.className = 'list-icon';
      icon.textContent = type === 'video' ? '🎞️' : '🖼';

      const nm = document.createElement('span');
      nm.className = 'list-name';
      nm.textContent = name;

      btn.appendChild(icon);
      btn.appendChild(nm);

      const idx = i;
      btn.addEventListener('click', () => openFS(idx));
      li.appendChild(btn);
      ul.appendChild(li);
    }

    frag.appendChild(ul);
    container.appendChild(frag);
  }

  // ── Fullscreen viewer ───────────────────────────────────────

  function openFS(idx) {
    savedScrollY = window.scrollY;
    mediaIdx = idx;
    document.getElementById('fullscreen').style.display = 'block';
    document.getElementById('browse').style.display = 'none';
    document.getElementById('btn-close').focus();
    updateFSMedia();
  }

  function stopVideo() {
    const vid = document.getElementById('fs-vid');
    vid.pause();
    vid.removeAttribute('src');
    vid.load();
    vid.style.display = 'none';
  }

  function closeFS() {
    stopVideo();
    showControls();
    document.getElementById('fs-img').style.display = 'none';
    document.getElementById('fs-img').src = '';
    document.getElementById('fullscreen').style.display = 'none';
    document.getElementById('browse').style.display = 'block';

    if (browseModified) {
      browseModified = false;
      navigate(dirPath, 'replace').then(() => window.scrollTo(0, savedScrollY));
    } else {
      window.scrollTo(0, savedScrollY);
    }
  }

  function updateFSMedia() {
    const item = dirMedia[mediaIdx];
    const src = '/files/' + encPath(joinPath(dirPath, item.name));
    const img = document.getElementById('fs-img');
    const vid = document.getElementById('fs-vid');

    if (item.type === 'video') {
      img.style.display = 'none';
      img.src = '';
      vid.style.display = 'block';
      vid.src = src;
      vid.load();
    } else {
      stopVideo();
      img.style.display = 'block';
      img.src = src;
    }

    document.getElementById('fs-name').textContent = item.name;
    document.getElementById('fs-counter').textContent =
      (mediaIdx + 1) + ' / ' + dirMedia.length;
    document.getElementById('btn-prev').disabled = mediaIdx === 0;
    document.getElementById('btn-next').disabled = mediaIdx === dirMedia.length - 1;
  }

  function removeCurrentAndAdvance() {
    browseModified = true;
    dirMedia.splice(mediaIdx, 1);
    if (dirMedia.length === 0) { closeFS(); return; }
    if (mediaIdx >= dirMedia.length) mediaIdx = dirMedia.length - 1;
    updateFSMedia();
  }

  document.getElementById('btn-prev').addEventListener('click', () => {
    if (mediaIdx > 0) { mediaIdx--; updateFSMedia(); }
  });
  document.getElementById('btn-next').addEventListener('click', () => {
    if (mediaIdx < dirMedia.length - 1) { mediaIdx++; updateFSMedia(); }
  });
  document.getElementById('btn-close').addEventListener('click', closeFS);

  // ── Controls auto-hide on keyboard use ──────────────────────

  const fsEl = document.getElementById('fullscreen');

  function hideControls() {
    fsEl.classList.add('controls-hidden');
  }

  function showControls() {
    fsEl.classList.remove('controls-hidden');
  }

  fsEl.addEventListener('mousemove', showControls);
  fsEl.addEventListener('touchstart', showControls, { passive: true });

  // ── Keyboard shortcuts ────────────────────────────────────────

  document.addEventListener('keydown', e => {
    if (fsEl.style.display !== 'block') return;
    // Don't hijack keys when the video element itself has focus (user may be seeking)
    if (document.activeElement === document.getElementById('fs-vid')) return;

    let handled = false;
    if (e.key === 'ArrowLeft' && mediaIdx > 0) {
      mediaIdx--; updateFSMedia(); handled = true;
    } else if (e.key === 'ArrowRight' && mediaIdx < dirMedia.length - 1) {
      mediaIdx++; updateFSMedia(); handled = true;
    } else if (e.key === 'Escape') {
      closeFS(); handled = true;
    } else if (e.key === 'f' || e.key === 'F') {
      document.getElementById('btn-fav').click(); handled = true;
    } else if (e.key === 'Delete' || e.key === 'd' || e.key === 'D') {
      document.getElementById('btn-del').click(); handled = true;
    } else if (e.key === 'z' || e.key === 'Z') {
      toggleFitMode(); handled = true;
    }

    if (handled) {
      e.preventDefault();
      hideControls();
    }
  });

  async function postAction(endpoint) {
    const item = dirMedia[mediaIdx];
    // Release video resource before the server moves the file
    if (item.type === 'video') stopVideo();

    const path = joinPath(dirPath, item.name);
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      if (res.ok) return true;
      const d = await res.json().catch(() => ({}));
      showToast('Error: ' + (d.error || res.status));
    } catch { showToast('Network error'); }
    return false;
  }

  document.getElementById('btn-fav').addEventListener('click', async () => {
    if (await postAction('/api/favorite')) {
      showToast('★ Added to favorites');
      removeCurrentAndAdvance();
    }
  });

  document.getElementById('btn-del').addEventListener('click', async () => {
    if (await postAction('/api/delete')) {
      showToast('🗑 Moved to trash');
      removeCurrentAndAdvance();
    }
  });

  document.getElementById('btn-empty-trash').addEventListener('click', async () => {
    if (!confirm('Permanently delete ALL files in the trash folder?\nThis cannot be undone.')) return;
    try {
      const res = await fetch('/api/empty-trash', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dirPath }),
      });
      if (res.ok) {
        const d = await res.json();
        showToast(`🗑 Deleted ${d.deleted} item(s) from trash`);
        navigate(dirPath, 'replace');
      } else {
        const d = await res.json().catch(() => ({}));
        showToast('Error: ' + (d.error || res.status));
      }
    } catch { showToast('Network error'); }
  });

  document.getElementById('btn-empty-nonfavs').addEventListener('click', async () => {
    if (!confirm('Permanently delete all files in this folder that are NOT in the fav subfolder?\nThis cannot be undone.')) return;
    try {
      const res = await fetch('/api/empty-nonfavs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dirPath }),
      });
      if (res.ok) {
        const d = await res.json();
        showToast(`✂ Deleted ${d.deleted} non-fav file(s)`);
        navigate(dirPath, 'replace');
      } else {
        const d = await res.json().catch(() => ({}));
        showToast('Error: ' + (d.error || res.status));
      }
    } catch { showToast('Network error'); }
  });

  document.getElementById('btn-delete-dir').addEventListener('click', async () => {
    const dirName = dirPath.split('/').pop();
    if (!confirm(`Permanently delete the directory "${dirName}" and all its contents?\nThis cannot be undone.`)) return;
    const parentPath = dirPath.includes('/') ? dirPath.slice(0, dirPath.lastIndexOf('/')) : '';
    try {
      const res = await fetch('/api/delete-dir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dirPath }),
      });
      if (res.ok) {
        showToast(`🗑 Deleted "${dirName}"`);
        navigate(parentPath);
      } else {
        const d = await res.json().catch(() => ({}));
        showToast('Error: ' + (d.error || res.status));
      }
    } catch { showToast('Network error'); }
  });

  function showToast(msg) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2300);
  }

  // ── Boot ─────────────────────────────────────────────────────
  window.addEventListener('popstate', e => {
    const path = (e.state && e.state.path != null)
      ? e.state.path
      : (new URLSearchParams(location.search).get('path') ?? '');
    navigate(path, 'none');
  });

  const initPath = new URLSearchParams(location.search).get('path') ?? '';
  setViewMode(viewMode);
  navigate(initPath, 'replace');
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def err_json(self, msg: str, status: int = 400) -> None:
        self.send_json({'error': msg}, status)

    def read_json_body(self) -> dict | None:
        length = int(self.headers.get('Content-Length', 0))
        if not length:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        p = parsed.path
        qs = parse_qs(parsed.query)

        if p in ('/', '/index.html'):
            self._serve_html()
        elif p.startswith('/files/'):
            self._serve_media(unquote(p[len('/files/'):]))
        elif p == '/api/list':
            self._api_list(qs.get('path', [''])[0])
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        p = urlparse(self.path).path
        body = self.read_json_body()
        if not isinstance(body, dict) or 'path' not in body:
            self.err_json('missing path')
            return
        if p == '/api/favorite':
            self._api_move(body['path'], 'fav')
        elif p == '/api/delete':
            self._api_move(body['path'], 'trash')
        elif p == '/api/empty-trash':
            self._api_empty_trash(body['path'])
        elif p == '/api/empty-nonfavs':
            self._api_empty_nonfavs(body['path'])
        elif p == '/api/delete-dir':
            self._api_delete_dir(body['path'])
        else:
            self.send_error(404)

    # ── Route implementations ───────────────────────────────────

    def _serve_html(self) -> None:
        body = _HTML.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_media(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.send_error(400)
            return

        abs_path = resolve_safe(rel)
        if abs_path is None or abs_path.is_symlink() or not abs_path.is_file():
            self.send_error(404)
            return

        if abs_path.suffix.lower() not in ALL_MEDIA_EXTS:
            self.send_error(403)
            return

        mime = mimetypes.guess_type(abs_path.name)[
            0] or 'application/octet-stream'
        size = abs_path.stat().st_size
        range_header = self.headers.get('Range', '').strip()

        if range_header.startswith('bytes='):
            self._serve_range(abs_path, mime, size, range_header[6:])
        else:
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                with open(abs_path, 'rb') as f:
                    shutil.copyfileobj(f, self.wfile)
            except OSError:
                pass

    def _serve_range(self, path: Path, mime: str, size: int, spec: str) -> None:
        m = re.match(r'^(\d*)-(\d*)$', spec)
        if not m:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return

        s_str, e_str = m.group(1), m.group(2)
        if s_str:
            start = int(s_str)
            end = int(e_str) if e_str else size - 1
        else:
            if not e_str:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
            start = max(0, size - int(e_str))
            end = size - 1

        if start >= size or start > end:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return

        end = min(end, size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except OSError:
            pass

    def _api_list(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_path = resolve_safe(rel)
        if abs_path is None or abs_path.is_symlink() or not abs_path.is_dir():
            self.err_json('not found', 404)
            return

        try:
            entries = list(abs_path.iterdir())
        except PermissionError:
            self.err_json('permission denied', 403)
            return

        dirs = sorted(
            [e.name for e in entries if e.is_dir() and not e.is_symlink()],
            key=natural_key,
        )
        media = sorted(
            [e.name for e in entries
             if e.is_file() and not e.is_symlink()
             and e.suffix.lower() in ALL_MEDIA_EXTS],
            key=natural_key,
        )
        fav_dirs = [
            d for d in dirs
            if (abs_path / d / 'fav').is_dir() and not (abs_path / d / 'fav').is_symlink()
        ]
        self.send_json({
            'dirs': dirs,
            'fav_dirs': fav_dirs,
            'media': [{'name': n, 'type': media_type(n)} for n in media],
            'has_trash': 'trash' in dirs,
            'has_fav': 'fav' in dirs,
        })

    def _api_move(self, rel: str, dest_name: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_src = resolve_safe(rel)
        if abs_src is None or abs_src.is_symlink() or not abs_src.is_file():
            self.err_json('file not found', 404)
            return

        if abs_src.suffix.lower() not in ALL_MEDIA_EXTS:
            self.err_json('not a supported media file', 400)
            return

        dest_dir = safe_dest_dir(abs_src.parent, dest_name)
        if dest_dir is None:
            self.err_json(f'cannot create {dest_name} directory', 500)
            return

        dest = unique_dest(dest_dir, abs_src.name)
        try:
            shutil.move(str(abs_src), str(dest))
        except OSError as e:
            self.err_json(str(e), 500)
            return

        self.send_json({'ok': True, 'dest': str(dest.relative_to(ROOT))})

    def _api_empty_trash(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_dir = resolve_safe(rel)
        if abs_dir is None or abs_dir.is_symlink() or not abs_dir.is_dir():
            self.err_json('directory not found', 404)
            return

        trash_dir = abs_dir / 'trash'
        if trash_dir.is_symlink() or not trash_dir.is_dir():
            self.err_json('no trash directory', 404)
            return

        deleted = 0
        for entry in list(trash_dir.iterdir()):
            if entry.is_symlink():
                continue
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                deleted += 1
            except OSError:
                pass

        self.send_json({'ok': True, 'deleted': deleted})

    def _api_empty_nonfavs(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_dir = resolve_safe(rel)
        if abs_dir is None or abs_dir.is_symlink() or not abs_dir.is_dir():
            self.err_json('directory not found', 404)
            return

        fav_dir = abs_dir / 'fav'
        if fav_dir.is_symlink() or not fav_dir.is_dir():
            self.err_json('no fav directory', 404)
            return

        deleted = 0
        for entry in list(abs_dir.iterdir()):
            if entry.is_symlink() or entry.is_dir():
                continue
            if entry.suffix.lower() not in ALL_MEDIA_EXTS:
                continue
            try:
                entry.unlink()
                deleted += 1
            except OSError:
                pass

        self.send_json({'ok': True, 'deleted': deleted})

    def _api_delete_dir(self, rel: str) -> None:
        if not validate_rel_path(rel):
            self.err_json('invalid path', 400)
            return

        abs_dir = resolve_safe(rel)
        if abs_dir is None or abs_dir.is_symlink() or not abs_dir.is_dir():
            self.err_json('directory not found', 404)
            return

        # Refuse to delete root or a dir that has trash/fav (use other endpoints instead)
        if abs_dir == ROOT:
            self.err_json('cannot delete root', 400)
            return

        try:
            shutil.rmtree(abs_dir)
        except OSError as e:
            self.err_json(str(e), 500)
            return

        self.send_json({'ok': True})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global ROOT

    parser = argparse.ArgumentParser(
        description='Lightweight image/video gallery server.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n  gallery.py\n  gallery.py ~/Photos\n  gallery.py ~/Photos -p 9000',
    )
    parser.add_argument('root', nargs='?', default='.', metavar='PATH',
                        help='Root media directory (default: current directory)')
    parser.add_argument('-p', '--port', type=int, default=8000, metavar='PORT',
                        help='Port to listen on (default: 8000)')
    parser.add_argument('--host', default='127.0.0.1', metavar='HOST',
                        help='Interface to bind to (default: 127.0.0.1)')
    args = parser.parse_args()

    try:
        ROOT = Path(args.root).resolve(strict=True)
    except FileNotFoundError:
        print(f'Error: path not found: {args.root}', file=sys.stderr)
        sys.exit(1)

    if not ROOT.is_dir():
        print(f'Error: not a directory: {args.root}', file=sys.stderr)
        sys.exit(1)

    if args.host not in ('127.0.0.1', 'localhost', '::1'):
        print(
            f'Warning: binding to {args.host} exposes the gallery '
            f'(and file move/delete) to all reachable hosts.',
            file=sys.stderr,
        )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Serving {ROOT}')
    print(f'Open:   http://{args.host}:{args.port}')
    print('Press Ctrl-C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
