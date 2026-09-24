const CATALOG_URL = "data/catalog.json";
const chapterUrl = (slug, id) => `data/books/${slug}/chapters/${String(id).padStart(4, "0")}.json`;
const STORAGE = {
  theme: "van-cac:theme",
  fontSize: "van-cac:font-size",
  sidebarCollapsed: "van-cac:sidebar-collapsed",
  sidebarWidth: "van-cac:sidebar-width",
  bookOrder: "van-cac:library-book-order",
  sortMode: "van-cac:library-sort-mode",
};
const SIDEBAR = { collapseAt: 180, maxWidth: 520, defaultWidth: 300, keyboardStep: 20 };
const state = {
  catalog: null, manifest: null, currentId: null, currentSlug: null, fontSize: 20,
  sidebarWidth: SIDEBAR.defaultWidth, resizeCandidate: null, resizePointerId: null, resizeStartX: 0, resizeStartWidth: 0,
  sortMode: localStorage.getItem("van-cac:library-sort-mode") || "custom",
  isReordering: false,
};
const elements = {
  sidebar: document.querySelector("#sidebar"), tocToggle: document.querySelector("#open-toc"), backdrop: document.querySelector("#toc-backdrop"),
  title: document.querySelector("#book-title"), originalTitle: document.querySelector("#original-title"),
  author: document.querySelector("#book-author"), tags: document.querySelector("#book-tags"),
  chapterTotal: document.querySelector("#chapter-total"), search: document.querySelector("#chapter-search"),
  list: document.querySelector("#chapter-list"), content: document.querySelector("#chapter-content"),
  previous: document.querySelector("#previous-chapter"), next: document.querySelector("#next-chapter"),
  progress: document.querySelector("#reading-progress-bar"), fontLabel: document.querySelector("#font-size-label"),
  bookmark: document.querySelector("#bookmark-button"), reader: document.querySelector(".reader"),
  library: document.querySelector("#library"), bookList: document.querySelector("#book-list"), appShell: document.querySelector("#app-shell"),
  sidebarToggle: document.querySelector("#sidebar-toggle"), sidebarResizer: document.querySelector("#sidebar-resizer"),
  sortPills: document.querySelectorAll(".sort-pill"),
  reorderToggle: document.querySelector("#reorder-toggle"),
  resetOrderBtn: document.querySelector("#reset-order-btn"),
};

const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const bookStorage = (key) => `van-cac:${state.currentSlug}:${key}`;
const getChapter = (id) => state.manifest?.chapters.find((chapter) => chapter.id === id);
const currentIndex = () => state.manifest.chapters.findIndex((chapter) => chapter.id === state.currentId);

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = theme === "dark" ? "#191817" : "#f6f1e8";
  localStorage.setItem(STORAGE.theme, theme);
}
function toggleTheme() { setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"); }
function setFontSize(size) {
  state.fontSize = Math.max(16, Math.min(28, size));
  document.documentElement.style.setProperty("--reader-size", `${state.fontSize}px`);
  elements.fontLabel.textContent = state.fontSize;
  localStorage.setItem(STORAGE.fontSize, String(state.fontSize));
}
function setSidebarWidth(size, { persist = true } = {}) {
  state.sidebarWidth = Math.max(SIDEBAR.collapseAt, Math.min(SIDEBAR.maxWidth, Math.round(size)));
  document.documentElement.style.setProperty("--sidebar-width", `${state.sidebarWidth}px`);
  elements.sidebarResizer.setAttribute("aria-valuenow", String(state.sidebarWidth));
  if (persist) localStorage.setItem(STORAGE.sidebarWidth, String(state.sidebarWidth));
}
function setSidebarCollapsed(collapsed) {
  elements.appShell.classList.toggle("sidebar-collapsed", collapsed);
  elements.sidebarToggle.setAttribute("aria-pressed", String(collapsed));
  elements.sidebarToggle.textContent = collapsed ? "Hiện mục lục" : "Ẩn mục lục";
  elements.sidebarResizer.setAttribute("aria-hidden", String(collapsed));
  localStorage.setItem(STORAGE.sidebarCollapsed, String(collapsed));
}
function resizeFromPointer(clientX) {
  const width = Math.round(state.resizeStartWidth + clientX - state.resizeStartX);
  state.resizeCandidate = width;
  const collapseTarget = width < SIDEBAR.collapseAt;
  elements.appShell.classList.toggle("is-sidebar-collapse-target", collapseTarget);
  if (!collapseTarget) setSidebarWidth(width, { persist: false });
}
function startSidebarResize(event) {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  event.preventDefault();
  state.resizePointerId = event.pointerId;
  state.resizeStartX = event.clientX;
  state.resizeStartWidth = state.sidebarWidth;
  state.resizeCandidate = state.sidebarWidth;
  elements.appShell.classList.add("is-resizing");
  window.addEventListener("pointermove", moveSidebarResize);
  window.addEventListener("pointerup", endSidebarResize);
  window.addEventListener("pointercancel", endSidebarResize);
}
function moveSidebarResize(event) {
  if (event.pointerId === state.resizePointerId) resizeFromPointer(event.clientX);
}
function endSidebarResize(event) {
  if (!elements.appShell.classList.contains("is-resizing") || event.pointerId !== state.resizePointerId) return;
  elements.appShell.classList.remove("is-resizing", "is-sidebar-collapse-target");
  window.removeEventListener("pointermove", moveSidebarResize);
  window.removeEventListener("pointerup", endSidebarResize);
  window.removeEventListener("pointercancel", endSidebarResize);
  if (state.resizeCandidate < SIDEBAR.collapseAt) {
    setSidebarCollapsed(true);
  } else {
    setSidebarCollapsed(false);
    setSidebarWidth(state.sidebarWidth);
  }
  state.resizeCandidate = null;
  state.resizePointerId = null;
  state.resizeStartX = 0;
  state.resizeStartWidth = 0;
}
function handleResizerKeydown(event) {
  if (event.key === "Home") { event.preventDefault(); return setSidebarCollapsed(true); }
  if (event.key === "End") { event.preventDefault(); setSidebarCollapsed(false); return setSidebarWidth(SIDEBAR.maxWidth); }
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  event.preventDefault();
  setSidebarCollapsed(false);
  setSidebarWidth(state.sidebarWidth + (event.key === "ArrowLeft" ? -SIDEBAR.keyboardStep : SIDEBAR.keyboardStep));
}
function setTags(target, genres) { target.replaceChildren(...genres.map((genre) => Object.assign(document.createElement("span"), { textContent: genre }))); }

function getCustomOrder() {
  try {
    const raw = localStorage.getItem(STORAGE.bookOrder);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function saveCustomOrder(order) {
  localStorage.setItem(STORAGE.bookOrder, JSON.stringify(order));
  updateResetButtonState();
}

function updateResetButtonState() {
  if (elements.resetOrderBtn) {
    elements.resetOrderBtn.hidden = !getCustomOrder();
  }
}

function getSortedBooks() {
  if (!state.catalog?.books) return [];
  const books = [...state.catalog.books];
  const mode = state.sortMode;

  if (mode === "recent") {
    return books.sort((a, b) => {
      const lastA = Number(localStorage.getItem(`van-cac:${a.slug}:last-chapter`)) || 0;
      const lastB = Number(localStorage.getItem(`van-cac:${b.slug}:last-chapter`)) || 0;
      if (lastA !== lastB) return lastB - lastA;
      return (a.order ?? 999) - (b.order ?? 999);
    });
  }

  if (mode === "chapters") {
    return books.sort((a, b) => {
      if (b.chapterCount !== a.chapterCount) return b.chapterCount - a.chapterCount;
      return (a.order ?? 999) - (b.order ?? 999);
    });
  }

  if (mode === "title") {
    return books.sort((a, b) => a.title.localeCompare(b.title, "vi"));
  }

  // mode === "custom"
  const customOrder = getCustomOrder();
  if (customOrder) {
    return books.sort((a, b) => {
      const idxA = customOrder.indexOf(a.slug);
      const idxB = customOrder.indexOf(b.slug);
      const posA = idxA !== -1 ? idxA : (a.order ?? 999) + 100;
      const posB = idxB !== -1 ? idxB : (b.order ?? 999) + 100;
      return posA - posB;
    });
  }

  return books.sort((a, b) => (a.order ?? 999) - (b.order ?? 999));
}

function moveBook(slug, offset) {
  const books = getSortedBooks();
  const currentIndex = books.findIndex((b) => b.slug === slug);
  if (currentIndex === -1) return;
  const targetIndex = currentIndex + offset;
  if (targetIndex < 0 || targetIndex >= books.length) return;

  const slugs = books.map((b) => b.slug);
  const [removed] = slugs.splice(currentIndex, 1);
  slugs.splice(targetIndex, 0, removed);

  state.sortMode = "custom";
  localStorage.setItem(STORAGE.sortMode, "custom");
  saveCustomOrder(slugs);
  renderLibrary();
}

function swapBooks(sourceSlug, targetSlug) {
  if (!sourceSlug || !targetSlug || sourceSlug === targetSlug) return;
  const books = getSortedBooks();
  const sourceIndex = books.findIndex((b) => b.slug === sourceSlug);
  const targetIndex = books.findIndex((b) => b.slug === targetSlug);
  if (sourceIndex === -1 || targetIndex === -1) return;

  const slugs = books.map((b) => b.slug);
  const [removed] = slugs.splice(sourceIndex, 1);
  slugs.splice(targetIndex, 0, removed);

  state.sortMode = "custom";
  localStorage.setItem(STORAGE.sortMode, "custom");
  saveCustomOrder(slugs);
  renderLibrary();
}

function setSortMode(mode) {
  state.sortMode = mode;
  localStorage.setItem(STORAGE.sortMode, mode);
  renderLibrary();
}

function toggleReorderMode() {
  state.isReordering = !state.isReordering;
  if (state.isReordering && state.sortMode !== "custom") {
    state.sortMode = "custom";
    localStorage.setItem(STORAGE.sortMode, "custom");
  }
  renderLibrary();
}

function resetCustomOrder() {
  localStorage.removeItem(STORAGE.bookOrder);
  state.sortMode = "custom";
  localStorage.setItem(STORAGE.sortMode, "custom");
  updateResetButtonState();
  renderLibrary();
}

function renderLibrary() {
  const template = document.querySelector("#book-card-template");
  const fragment = document.createDocumentFragment();
  const books = getSortedBooks();

  elements.library.classList.toggle("is-reordering-mode", state.isReordering);
  if (elements.reorderToggle) {
    elements.reorderToggle.classList.toggle("is-active", state.isReordering);
    elements.reorderToggle.setAttribute("aria-pressed", String(state.isReordering));
    elements.reorderToggle.innerHTML = state.isReordering
      ? '<span aria-hidden="true">✓</span> Xong sắp xếp'
      : '<span aria-hidden="true">⇅</span> Sắp xếp vị trí';
  }
  for (const pill of elements.sortPills) {
    const isActive = pill.dataset.sort === state.sortMode;
    pill.classList.toggle("is-active", isActive);
    pill.setAttribute("aria-selected", String(isActive));
  }
  updateResetButtonState();

  books.forEach((book, index) => {
    const item = template.content.firstElementChild.cloneNode(true);
    item.dataset.slug = book.slug;
    const card = item.querySelector(".book-card");
    card.href = `?book=${encodeURIComponent(book.slug)}`;
    card.querySelector(".book-card-mark").textContent = book.title.slice(0, 1).toUpperCase();
    card.querySelector(".book-status").textContent = `${book.status} · ${book.chapterCount} chương`;
    card.querySelector(".book-card-title").textContent = book.title;
    card.querySelector(".book-card-original").textContent = book.originalTitle || "";
    card.querySelector(".book-card-author").textContent = `Tác giả: ${book.author}`;
    card.querySelector(".book-card-summary").textContent = book.description || "Chưa có mô tả cho tác phẩm này.";
    const savedChapter = Number(localStorage.getItem(`van-cac:${book.slug}:last-chapter`));
    card.querySelector(".book-card-action").textContent = savedChapter > 0
      ? `Đọc tiếp · Chương ${savedChapter} →`
      : "Bắt đầu đọc →";
    setTags(card.querySelector(".book-card-tags"), book.genres);

    const upBtn = item.querySelector(".btn-move-up");
    const downBtn = item.querySelector(".btn-move-down");
    if (upBtn) {
      upBtn.disabled = index === 0;
      upBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        moveBook(book.slug, -1);
      });
    }
    if (downBtn) {
      downBtn.disabled = index === books.length - 1;
      downBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        moveBook(book.slug, 1);
      });
    }

    item.draggable = state.isReordering;
    item.addEventListener("dragstart", (e) => {
      if (!state.isReordering) return e.preventDefault();
      item.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", book.slug);
    });
    item.addEventListener("dragend", () => {
      item.classList.remove("is-dragging");
      document.querySelectorAll(".book-card-item").forEach((el) => el.classList.remove("drag-over"));
    });
    item.addEventListener("dragover", (e) => {
      if (!state.isReordering) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      item.classList.add("drag-over");
    });
    item.addEventListener("dragleave", () => {
      item.classList.remove("drag-over");
    });
    item.addEventListener("drop", (e) => {
      if (!state.isReordering) return;
      e.preventDefault();
      item.classList.remove("drag-over");
      const sourceSlug = e.dataTransfer.getData("text/plain");
      swapBooks(sourceSlug, book.slug);
    });

    fragment.append(item);
  });
  elements.bookList.replaceChildren(fragment);
}
function renderBookDetails() {
  const { book, chapterCount } = state.manifest;
  elements.title.textContent = book.title;
  elements.originalTitle.textContent = book.originalTitle || "";
  elements.author.textContent = `Tác giả: ${book.author}`;
  elements.chapterTotal.textContent = `${book.status} · hiện có ${chapterCount} chương`;
  setTags(elements.tags, book.genres);
}
function renderChapterList(query = "") {
  const normalizedQuery = normalize(query.trim()), fragment = document.createDocumentFragment();
  const chapters = state.manifest.chapters.filter((chapter) => normalize(`${chapter.id} ${chapter.title}`).includes(normalizedQuery));
  if (!chapters.length) fragment.append(Object.assign(document.createElement("p"), { className: "empty-state", textContent: "Không tìm thấy chương phù hợp." }));
  const template = document.querySelector("#chapter-item-template");
  for (const chapter of chapters) {
    const item = template.content.firstElementChild.cloneNode(true); item.dataset.chapterId = chapter.id;
    item.setAttribute("aria-current", chapter.id === state.currentId ? "page" : "false");
    item.querySelector(".chapter-number").textContent = `Ch. ${chapter.id}`;
    item.querySelector(".chapter-name").textContent = chapter.title.replace(/^Chương\s+\d+\s*:\s*/i, "");
    item.addEventListener("click", () => loadChapter(chapter.id)); fragment.append(item);
  }
  elements.list.replaceChildren(fragment);
}
function renderChapter(chapter) {
  const article = document.createDocumentFragment();
  article.append(Object.assign(document.createElement("h2"), { textContent: chapter.title }));
  const minutes = Math.max(1, Math.ceil(chapter.characterCount / 900));
  article.append(Object.assign(document.createElement("p"), { className: "chapter-meta", textContent: `${chapter.characterCount.toLocaleString("vi-VN")} ký tự · khoảng ${minutes} phút đọc` }));
  const body = Object.assign(document.createElement("div"), { className: "chapter-body" });
  for (const paragraph of chapter.content.split(/\n\s*\n/)) if (paragraph.trim()) body.append(Object.assign(document.createElement("p"), { textContent: paragraph.trim() }));
  article.append(body); elements.content.replaceChildren(article);
}
function updateNavigation() {
  const index = currentIndex(), previous = state.manifest.chapters[index - 1], next = state.manifest.chapters[index + 1];
  for (const [element, chapter, fallback] of [[elements.previous, previous, "← Chương trước"], [elements.next, next, "Chương sau →"]]) {
    element.disabled = !chapter; element.dataset.chapterId = chapter?.id ?? "";
    element.textContent = chapter ? (element === elements.previous ? `← Chương ${chapter.id}` : `Chương ${chapter.id} →`) : fallback;
  }
}
function updateBookmarkButton() { elements.bookmark.textContent = Number(localStorage.getItem(bookStorage("bookmark"))) === state.currentId ? "Đã đánh dấu" : "Đánh dấu chương này"; }
function updateUrl() { const url = new URL(location.href); url.search = ""; url.searchParams.set("book", state.currentSlug); url.searchParams.set("chapter", state.currentId); history.replaceState({}, "", url); }
function showReader() {
  elements.library.hidden = true; elements.reader.hidden = false; elements.sidebar.hidden = false;
  elements.sidebarResizer.hidden = elements.appShell.classList.contains("sidebar-collapsed");
  elements.tocToggle.hidden = false;
}
function showLibrary() {
  state.currentSlug = null; state.currentId = null; elements.reader.hidden = true; elements.sidebar.hidden = true;
  elements.sidebarResizer.hidden = true; elements.library.hidden = false;
  elements.tocToggle.hidden = true; document.title = `${state.catalog.libraryTitle} — Thư viện truyện`;
  history.replaceState({}, "", location.pathname); closeToc(); window.scrollTo({ top: 0, behavior: "auto" });
}
async function loadChapter(id, { scroll = true } = {}) {
  if (!getChapter(id) || id === state.currentId) return;
  elements.content.replaceChildren(Object.assign(document.createElement("p"), { className: "loading", textContent: "Đang mở chương…" }));
  try {
    const response = await fetch(chapterUrl(state.currentSlug, id)); if (!response.ok) throw new Error(`Không tải được chương ${id}`);
    const chapter = await response.json(); state.currentId = id; renderChapter(chapter); renderChapterList(elements.search.value); updateNavigation(); updateBookmarkButton(); updateUrl();
    localStorage.setItem(bookStorage("last-chapter"), String(id)); document.title = `${chapter.title} — ${state.manifest.book.title}`; closeToc(); if (scroll) window.scrollTo({ top: 0, behavior: "auto" });
  } catch (error) { elements.content.replaceChildren(Object.assign(document.createElement("p"), { className: "empty-state", textContent: "Không thể tải chương này. Hãy thử tải lại trang." })); console.error(error); }
}
async function openBook(slug, { scroll = false } = {}) {
  if (!state.catalog.books.some((book) => book.slug === slug)) return showLibrary();
  try {
    const response = await fetch(`data/books/${slug}/manifest.json`); if (!response.ok) throw new Error(`Không tải được tác phẩm ${slug}`);
    state.manifest = await response.json(); state.currentSlug = slug; state.currentId = null; elements.search.value = ""; showReader(); renderBookDetails();
    const params = new URLSearchParams(location.search), requested = Number(params.get("chapter")), saved = Number(localStorage.getItem(bookStorage("last-chapter")));
    const initial = getChapter(requested) || getChapter(saved) || state.manifest.chapters[0]; await loadChapter(initial.id, { scroll });
  } catch (error) { showReader(); elements.content.replaceChildren(Object.assign(document.createElement("p"), { className: "empty-state", textContent: "Không thể mở tác phẩm này." })); console.error(error); }
}
function toggleBookmark() { if (!state.currentId) return; const key = bookStorage("bookmark"); Number(localStorage.getItem(key)) === state.currentId ? localStorage.removeItem(key) : localStorage.setItem(key, String(state.currentId)); updateBookmarkButton(); }
function closeToc() {
  elements.sidebar.classList.remove("is-open"); elements.tocToggle?.setAttribute("aria-expanded", "false");
  elements.backdrop.hidden = true; document.body.classList.remove("toc-open");
}
function toggleToc() {
  const open = elements.sidebar.classList.toggle("is-open"); elements.tocToggle.setAttribute("aria-expanded", String(open));
  elements.backdrop.hidden = !open; document.body.classList.toggle("toc-open", open);
}
function updateProgress() { const max = document.documentElement.scrollHeight - innerHeight; elements.progress.style.width = `${Math.min(100, Math.max(0, max > 0 ? scrollY / max * 100 : 0))}%`; }
function bindEvents() {
  document.querySelector("#theme-toggle").addEventListener("click", toggleTheme); document.querySelector("#font-decrease").addEventListener("click", () => setFontSize(state.fontSize - 1)); document.querySelector("#font-increase").addEventListener("click", () => setFontSize(state.fontSize + 1));
  elements.sidebarToggle.addEventListener("click", () => setSidebarCollapsed(!elements.appShell.classList.contains("sidebar-collapsed")));
  elements.sidebarResizer.addEventListener("pointerdown", startSidebarResize); elements.sidebarResizer.addEventListener("keydown", handleResizerKeydown);
  elements.search.addEventListener("input", (event) => renderChapterList(event.target.value)); elements.previous.addEventListener("click", () => loadChapter(Number(elements.previous.dataset.chapterId))); elements.next.addEventListener("click", () => loadChapter(Number(elements.next.dataset.chapterId))); elements.bookmark.addEventListener("click", toggleBookmark); elements.tocToggle?.addEventListener("click", toggleToc); elements.backdrop.addEventListener("click", closeToc);
  for (const link of document.querySelectorAll("#home-link, #library-link")) link.addEventListener("click", (event) => { event.preventDefault(); showLibrary(); });
  elements.sortPills.forEach((pill) => {
    pill.addEventListener("click", () => setSortMode(pill.dataset.sort));
  });
  elements.reorderToggle?.addEventListener("click", toggleReorderMode);
  elements.resetOrderBtn?.addEventListener("click", resetCustomOrder);
  addEventListener("scroll", updateProgress, { passive: true }); addEventListener("resize", updateProgress); addEventListener("popstate", () => { const slug = new URLSearchParams(location.search).get("book"); slug ? openBook(slug) : showLibrary(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") return closeToc(); if (event.target.matches("input, textarea") || !state.currentSlug) return; if (event.key === "ArrowLeft" && !elements.previous.disabled) elements.previous.click(); if (event.key === "ArrowRight" && !elements.next.disabled) elements.next.click(); });
}
async function start() {
  setTheme(localStorage.getItem(STORAGE.theme) || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")); setFontSize(Number(localStorage.getItem(STORAGE.fontSize)) || 20);
  setSidebarWidth(Number(localStorage.getItem(STORAGE.sidebarWidth)) || SIDEBAR.defaultWidth); setSidebarCollapsed(localStorage.getItem(STORAGE.sidebarCollapsed) === "true"); bindEvents();
  try { const response = await fetch(CATALOG_URL); if (!response.ok) throw new Error("Không tải được catalog"); state.catalog = await response.json(); renderLibrary(); const slug = new URLSearchParams(location.search).get("book"); slug ? await openBook(slug) : showLibrary(); }
  catch (error) { elements.library.hidden = false; elements.library.replaceChildren(Object.assign(document.createElement("p"), { className: "empty-state", textContent: "Không thể mở thư viện. Hãy chạy lệnh tạo dữ liệu trước khi xem tại máy." })); console.error(error); }
}
start();
