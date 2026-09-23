/**
 * Перетаскиваемые разделители боковых панелей.
 * Размеры сохраняются в localStorage.
 */

const STORAGE_SIDEBAR = "rhyme-ui-sidebar-w";
const STORAGE_JOURNAL = "rhyme-ui-journal-w";

const DEFAULT_SIDEBAR = 400;
const DEFAULT_JOURNAL = 340;

/** Подключает ресайз левой и правой колонок. */
export function initResizers() {
  initSidebarResize();
  initJournalResize();
}

/** Ширина левой колонки (форма). */
function initSidebarResize() {
  const splitter = document.getElementById("splitter-sidebar");
  if (!splitter) return;

  const min = 280;
  const maxRatio = 0.5;
  const saved = parseInt(localStorage.getItem(STORAGE_SIDEBAR) || "", 10);
  setSidebarWidth(Number.isFinite(saved) ? saved : DEFAULT_SIDEBAR);

  let dragging = false;

  const onMove = (clientX) => {
    const max = Math.floor(window.innerWidth * maxRatio);
    const w = Math.min(Math.max(clientX, min), max);
    setSidebarWidth(w);
  };

  const stop = () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("is-resizing-v");
    splitter.classList.remove("active");
    const w = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w"),
      10
    );
    if (Number.isFinite(w)) localStorage.setItem(STORAGE_SIDEBAR, String(w));
  };

  splitter.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    document.body.classList.add("is-resizing-v");
    splitter.classList.add("active");
    e.preventDefault();
  });

  splitter.addEventListener("dblclick", () => {
    setSidebarWidth(DEFAULT_SIDEBAR);
    localStorage.setItem(STORAGE_SIDEBAR, String(DEFAULT_SIDEBAR));
  });

  splitter.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 48 : 16;
    const cur = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w"),
      10
    );
    if (e.key === "ArrowLeft") {
      setSidebarWidth(cur - step);
      localStorage.setItem(STORAGE_SIDEBAR, String(cur - step));
      e.preventDefault();
    }
    if (e.key === "ArrowRight") {
      setSidebarWidth(cur + step);
      localStorage.setItem(STORAGE_SIDEBAR, String(cur + step));
      e.preventDefault();
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    onMove(e.clientX);
  });
  window.addEventListener("mouseup", stop);
}

function setSidebarWidth(px) {
  const min = 280;
  const max = Math.floor(window.innerWidth * 0.5);
  const w = Math.min(Math.max(px, min), max);
  document.documentElement.style.setProperty("--sidebar-w", `${w}px`);
}

/** Ширина правой колонки (журнал). */
function initJournalResize() {
  const splitter = document.getElementById("splitter-journal");
  if (!splitter) return;

  const min = 260;
  const maxRatio = 0.45;
  const saved = parseInt(localStorage.getItem(STORAGE_JOURNAL) || "", 10);
  setJournalWidth(Number.isFinite(saved) ? saved : DEFAULT_JOURNAL);

  let dragging = false;

  const onMove = (clientX) => {
    const max = Math.floor(window.innerWidth * maxRatio);
    const w = Math.min(Math.max(window.innerWidth - clientX, min), max);
    setJournalWidth(w);
  };

  const stop = () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("is-resizing-v");
    splitter.classList.remove("active");
    const w = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue("--journal-w"),
      10
    );
    if (Number.isFinite(w)) localStorage.setItem(STORAGE_JOURNAL, String(w));
  };

  splitter.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    document.body.classList.add("is-resizing-v");
    splitter.classList.add("active");
    e.preventDefault();
  });

  splitter.addEventListener("dblclick", () => {
    setJournalWidth(DEFAULT_JOURNAL);
    localStorage.setItem(STORAGE_JOURNAL, String(DEFAULT_JOURNAL));
  });

  splitter.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 48 : 16;
    const cur = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue("--journal-w"),
      10
    );
    if (e.key === "ArrowLeft") {
      setJournalWidth(cur + step);
      localStorage.setItem(STORAGE_JOURNAL, String(cur + step));
      e.preventDefault();
    }
    if (e.key === "ArrowRight") {
      setJournalWidth(cur - step);
      localStorage.setItem(STORAGE_JOURNAL, String(cur - step));
      e.preventDefault();
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    onMove(e.clientX);
  });
  window.addEventListener("mouseup", stop);

  window.addEventListener("resize", () => {
    const cur = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w"),
      10
    );
    if (Number.isFinite(cur)) setSidebarWidth(cur);
    const jw = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue("--journal-w"),
      10
    );
    if (Number.isFinite(jw)) setJournalWidth(jw);
  });
}

function setJournalWidth(px) {
  const min = 260;
  const max = Math.floor(window.innerWidth * 0.45);
  const w = Math.min(Math.max(px, min), max);
  document.documentElement.style.setProperty("--journal-w", `${w}px`);
}
