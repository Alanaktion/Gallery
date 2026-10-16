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

function inFavDir() {
  return dirPath.split('/').pop() === 'fav';
}

function inTrashDir() {
  return dirPath.split('/').pop() === 'trash';
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

// 'contain' scales images up to fill the viewport; 'scale-down' only shrinks them
if (fitMode !== 'contain') fitMode = 'scale-down';

function applyFitMode() {
  document.getElementById('fs-img').style.objectFit = fitMode;
  document.getElementById('fs-vid').style.objectFit = fitMode;
  document.getElementById('btn-fit').classList.toggle('active', fitMode === 'contain');
  clearTimeout(zoomTimer);
  setZoom(false);
}

function toggleFitMode() {
  fitMode = fitMode === 'scale-down' ? 'contain' : 'scale-down';
  localStorage.setItem('galleryFit', fitMode);
  applyFitMode();
}

document.getElementById('btn-fit').addEventListener('click', toggleFitMode);

// ── Click-to-zoom (actual size) with panning ────────────────

const fsStage = document.getElementById('fs-stage');
const fsImg = document.getElementById('fs-img');
let zoomed = false;
let zoomTimer = null;
let drag = null;  // {x, y, left, top, moved} while a mouse drag-pan is in progress

// Scale the image is currently rendered at when not zoomed
function fitScale() {
  const nw = fsImg.naturalWidth, nh = fsImg.naturalHeight;
  if (!nw || !nh) return 1;
  const fit = Math.min(fsStage.clientWidth / nw, fsStage.clientHeight / nh);
  return fitMode === 'scale-down' ? Math.min(1, fit) : fit;
}

function updateZoomable() {
  fsImg.classList.toggle('zoomable', !zoomed && Math.abs(fitScale() - 1) > 0.001);
}

// Toggle actual size, keeping the clicked point under the cursor when zooming in
function setZoom(on, clientX, clientY) {
  if (on && !fsImg.classList.contains('zoomable')) return;
  if (on === zoomed) { updateZoomable(); return; }

  let fx = 0, fy = 0, ox = 0, oy = 0;
  if (on && clientX != null) {
    const rect = fsStage.getBoundingClientRect();
    const s = fitScale();
    ox = clientX - rect.left;
    oy = clientY - rect.top;
    // Position of the click in image pixels, accounting for object-fit centering
    fx = (ox - (rect.width - fsImg.naturalWidth * s) / 2) / s;
    fy = (oy - (rect.height - fsImg.naturalHeight * s) / 2) / s;
    fx = Math.max(0, Math.min(fsImg.naturalWidth, fx));
    fy = Math.max(0, Math.min(fsImg.naturalHeight, fy));
  }

  zoomed = on;
  fsStage.classList.toggle('zoomed', on);
  fsStage.classList.remove('dragging');
  drag = null;
  if (on) {
    fsStage.scrollLeft = fsImg.offsetLeft + fx - ox;
    fsStage.scrollTop = fsImg.offsetTop + fy - oy;
  } else {
    fsStage.scrollLeft = fsStage.scrollTop = 0;
  }
  updateZoomable();
}

fsImg.addEventListener('load', updateZoomable);
window.addEventListener('resize', updateZoomable);

fsImg.addEventListener('click', e => {
  if (e.button !== 0) return;
  if (drag && drag.moved) { drag = null; return; }
  drag = null;
  // Delay so a double-click (browser fullscreen) doesn't also toggle zoom
  clearTimeout(zoomTimer);
  if (e.detail > 1) return;
  const { clientX, clientY } = e;
  zoomTimer = setTimeout(() => setZoom(!zoomed, clientX, clientY), 250);
});

fsImg.addEventListener('pointerdown', e => {
  if (!zoomed || e.button !== 0 || e.pointerType !== 'mouse') return;
  drag = { x: e.clientX, y: e.clientY, left: fsStage.scrollLeft, top: fsStage.scrollTop, moved: false };
  fsImg.setPointerCapture(e.pointerId);
});

fsImg.addEventListener('pointermove', e => {
  if (!drag || !fsImg.hasPointerCapture(e.pointerId)) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (!drag.moved && Math.hypot(dx, dy) < 4) return;
  drag.moved = true;
  fsStage.classList.add('dragging');
  fsStage.scrollLeft = drag.left - dx;
  fsStage.scrollTop = drag.top - dy;
});

fsImg.addEventListener('pointerup', () => fsStage.classList.remove('dragging'));
fsImg.addEventListener('pointercancel', () => { fsStage.classList.remove('dragging'); drag = null; });

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
  document.getElementById('btn-empty-trash').style.display = data.has_trash && data.can_delete ? '' : 'none';
  const showEmptyNonFavs = data.has_fav && data.media.length && data.can_delete;
  document.getElementById('btn-empty-nonfavs').style.display = showEmptyNonFavs ? '' : 'none';
  // Server rejects favoriting fav/ and trash/ dirs or dirs already inside a fav/
  const parts = dirPath.split('/');
  const showFavDir = dirPath !== '' && data.can_fav
    && !['fav', 'trash'].includes(parts.at(-1)) && parts.at(-2) !== 'fav';
  document.getElementById('btn-favdir').style.display = showFavDir ? '' : 'none';
  updateFavBtn(data);
  document.getElementById('btn-del').style.display = inTrashDir() ? 'none' : '';
  const showDeleteDir = dirPath !== '' && data.can_delete && !data.has_trash && !data.has_fav && !data.dirs.length;
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
    bindOpenFS(item, i);
    grid.appendChild(item);
  }

  container.appendChild(grid);
}

function mediaHref(name) {
  return '/files/' + encPath(joinPath(dirPath, name));
}

function bindOpenFS(el, idx) {
  el.addEventListener('click', e => {
    if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      openFS(idx);
    }
  });
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
  const item = document.createElement('a');
  item.className = 'item';
  item.href = mediaHref(name);

  const thumb = document.createElement('img');
  thumb.className = 'item-thumb';
  thumb.src = mediaHref(name);
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
  const item = document.createElement('a');
  item.className = 'item';
  item.href = mediaHref(name);

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

    const btn = document.createElement('a');
    btn.className = 'list-btn';
    btn.href = mediaHref(name);

    const icon = document.createElement('span');
    icon.className = 'list-icon';
    icon.textContent = type === 'video' ? '🎞️' : '🖼';

    const nm = document.createElement('span');
    nm.className = 'list-name';
    nm.textContent = name;

    btn.appendChild(icon);
    btn.appendChild(nm);

    bindOpenFS(btn, i);
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
  setZoom(false);
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
  const src = mediaHref(item.name);
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
  applyFitMode();
  preloadNext();
}

let preloadImg = null;
function preloadNext() {
  const next = dirMedia[mediaIdx + 1];
  if (!next || next.type !== 'image') return;
  preloadImg = new Image();
  preloadImg.src = mediaHref(next.name);
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

// Capture phase on window so these run before a focused <video>'s built-in
// controls, which would otherwise consume keys like arrows and space
window.addEventListener('keydown', e => {
  // Leave browser shortcuts (Ctrl+F, Ctrl+D, Alt+←, …) alone
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  if (e.key === 'Backspace' && fsEl.style.display !== 'block' && dirPath !== '') {
    const parentPath = dirPath.includes('/') ? dirPath.slice(0, dirPath.lastIndexOf('/')) : '';
    navigate(parentPath);
    e.preventDefault();
    return;
  }

  if (fsEl.style.display !== 'block') return;

  const vid = document.getElementById('fs-vid');
  const isVideo = vid.style.display === 'block';
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  let handled = true;

  // Video-specific shortcuts (active whenever a video is open). Space is
  // always consumed so it can't activate a focused button (e.g. close).
  if (key === ' ' || (isVideo && key === 'p')) {
    if (isVideo) vid.paused ? vid.play() : vid.pause();
  } else if (isVideo && (key === 'j' || (e.shiftKey && key === 'ArrowLeft'))) {
    vid.currentTime = Math.max(0, vid.currentTime - (key === 'j' ? 10 : 5));
  } else if (isVideo && (key === 'k' || (e.shiftKey && key === 'ArrowRight'))) {
    vid.currentTime = Math.min(vid.duration || Infinity, vid.currentTime + (key === 'k' ? 10 : 5));
  } else if (isVideo && key === 'l') {
    vid.loop = !vid.loop;
    showToast(vid.loop ? '🔁 Loop on' : '🔁 Loop off');
  } else if (isVideo && key === 'm') {
    vid.muted = !vid.muted;
    showToast(vid.muted ? '🔇 Muted' : '🔊 Unmuted');
  } else if (isVideo && (key === 'ArrowUp' || key === 'ArrowDown')) {
    const step = key === 'ArrowUp' ? 0.1 : -0.1;
    vid.volume = Math.round(Math.min(1, Math.max(0, vid.volume + step)) * 10) / 10;
    vid.muted = false;
    showToast('🔊 ' + Math.round(vid.volume * 100) + '%');
  }
  // Global fullscreen shortcuts. Keys are consumed even when they're a no-op
  // (first/last item, hidden button) so the video player doesn't act on them.
  else if (key === 'ArrowLeft') {
    if (mediaIdx > 0) { mediaIdx--; updateFSMedia(); }
  } else if (key === 'ArrowRight') {
    if (mediaIdx < dirMedia.length - 1) { mediaIdx++; updateFSMedia(); }
  } else if (key === 'Escape') {
    if (zoomed) setZoom(false);
    else closeFS();
  } else if (key === 'f') {
    const btn = document.getElementById('btn-fav');
    if (btn.style.display !== 'none') btn.click();
  } else if (key === 'Delete' || key === 'd') {
    const btn = document.getElementById('btn-del');
    if (btn.style.display !== 'none') btn.click();
  } else if (key === 'z') {
    toggleFitMode();
  } else {
    handled = false;
  }

  if (handled) {
    e.preventDefault();
    e.stopPropagation();
    hideControls();
  }
}, true);

// Buttons activate on Space keyup, so cancel that too while the viewer is open
window.addEventListener('keyup', e => {
  if (e.key === ' ' && fsEl.style.display === 'block') {
    e.preventDefault();
    e.stopPropagation();
  }
}, true);

let actionPending = false;  // prevents acting on the same item twice before it's removed

async function postAction(endpoint) {
  if (actionPending) return false;
  actionPending = true;
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
  } catch {
    showToast('Network error');
  } finally {
    actionPending = false;
  }
  // Reload the video stopped above
  if (item.type === 'video' && fsEl.style.display === 'block') updateFSMedia();
  return false;
}

// In a fav/ dir the fav button un-favorites; elsewhere it's hidden if favoriting is blocked
function updateFavBtn(data) {
  const btn = document.getElementById('btn-fav');
  const unfav = inFavDir();
  btn.style.display = unfav || data.can_fav ? '' : 'none';
  btn.classList.toggle('active', unfav);
  btn.title = unfav ? 'Remove from favorites (F)' : 'Add to favorites (F)';
}

document.getElementById('btn-fav').addEventListener('click', async () => {
  if (inFavDir()) {
    if (await postAction('/api/unfavorite')) {
      showToast('☆ Removed from favorites');
      removeCurrentAndAdvance();
    }
  } else if (await postAction('/api/favorite')) {
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
  // Replace any visible toast so rapid repeats (e.g. volume) don't stack
  document.querySelectorAll('.toast').forEach(t => t.remove());
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
