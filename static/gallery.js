'use strict';

let dirPath = '';       // current directory (relative from root, no leading/trailing slash)
let dirMedia = [];      // [{name, type}] in current directory
let mediaIdx = 0;       // index of current fullscreen item
let navToken = 0;       // guards against stale navigate() responses
let browseModified = false;  // true when a fav/delete happened in fullscreen
let savedScrollY = 0;
let fsHistoryPushed = false; // true when a fullscreen history entry is on the stack

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
  document.getElementById('btn-favdir').style.display = dirPath !== '' ? '' : 'none';
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

function openFS(idx, pushHistory = true) {
  savedScrollY = window.scrollY;
  mediaIdx = idx;
  document.getElementById('fullscreen').style.display = 'block';
  document.getElementById('browse').style.display = 'none';
  document.getElementById('btn-close').focus();
  if (pushHistory) {
    history.pushState({ path: dirPath, fullscreen: true, mediaIdx: idx }, '');
  }
  fsHistoryPushed = true;
  updateFSMedia();
}

function stopVideo() {
  const vid = document.getElementById('fs-vid');
  vid.pause();
  vid.removeAttribute('src');
  vid.load();
  vid.style.display = 'none';
}

function closeFSUI() {
  stopVideo();
  showControls();
  document.getElementById('fs-img').style.display = 'none';
  document.getElementById('fs-img').src = '';
  document.getElementById('fullscreen').style.display = 'none';
  document.getElementById('browse').style.display = 'block';
}

function closeFS(fromPopstate = false) {
  if (fsHistoryPushed && !fromPopstate) {
    // Let history.back() fire popstate, which calls closeFS(true) for real teardown
    fsHistoryPushed = false;
    history.back();
    return;
  }
  fsHistoryPushed = false;
  closeFSUI();
  if (fromPopstate) {
    // The popstate handler will call navigate() which handles any needed refresh
    browseModified = false;
    window.scrollTo(0, savedScrollY);
  } else if (browseModified) {
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
  if (fsHistoryPushed) {
    history.replaceState({ path: dirPath, fullscreen: true, mediaIdx }, '');
  }
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

function toggleBrowserFS(e) {
  if (e.button !== 0) {
    return;
  }
  e.preventDefault();
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
}

document.getElementById('fs-img').addEventListener('dblclick', toggleBrowserFS);
document.getElementById('fs-vid').addEventListener('dblclick', toggleBrowserFS);

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
  if (e.key === 'Backspace' && fsEl.style.display !== 'block' && dirPath !== '') {
    const parentPath = dirPath.includes('/') ? dirPath.slice(0, dirPath.lastIndexOf('/')) : '';
    navigate(parentPath);
    e.preventDefault();
    return;
  }

  if (fsEl.style.display !== 'block') return;

  const vid = document.getElementById('fs-vid');
  const isVideo = vid.style.display === 'block';
  let handled = false;
  let isVideoShortcut = false;

  // Video-specific shortcuts (active whenever a video is open)
  if (isVideo) {
    if (e.key === ' ' || e.key === 'p' || e.key === 'P') {
      vid.paused ? vid.play() : vid.pause();
      handled = true; isVideoShortcut = true;
    } else if (e.key === 'j' || e.key === 'J') {
      vid.currentTime = Math.max(0, vid.currentTime - 10);
      handled = true; isVideoShortcut = true;
    } else if (e.key === 'k' || e.key === 'K') {
      vid.currentTime = Math.min(vid.duration || Infinity, vid.currentTime + 10);
      handled = true; isVideoShortcut = true;
    } else if (e.key === 'l' || e.key === 'L') {
      vid.loop = !vid.loop;
      showToast(vid.loop ? '🔁 Loop on' : '🔁 Loop off');
      handled = true; isVideoShortcut = true;
    }
  }

  // Global fullscreen shortcuts
  if (!handled) {
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

document.getElementById('btn-favdir').addEventListener('click', async () => {
  try {
    const res = await fetch('/api/favdir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: dirPath }),
    });
    if (res.ok) {
      const d = await res.json();
      showToast('★ Folder added to favorites');
      navigate(d.dest);
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
  const state = e.state || {};

  if (state.fullscreen) {
    // Forward navigation back to a fullscreen state — restore only if dir still matches
    if (state.path === dirPath && state.mediaIdx < dirMedia.length) {
      openFS(state.mediaIdx, false);
    } else {
      navigate(state.path || '', 'none');
    }
    return;
  }

  const path = state.path != null
    ? state.path
    : (new URLSearchParams(location.search).get('path') ?? '');
  if (fsEl.style.display === 'block') {
    closeFS(true);
  }
  navigate(path, 'none');
});

const initPath = new URLSearchParams(location.search).get('path') ?? '';
setViewMode(viewMode);
navigate(initPath, 'replace');
