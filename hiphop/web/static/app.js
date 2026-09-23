/**
 * Веб-форма: блоки текста, выбор модели, SSE-прогресс анализа.
 */

import { initResizers } from "./resize.js";
import { renderReport } from "./report_renderer.js";
import { trackEvent } from "./analytics.js";
import {
  scanBlocksForParentheses,
  stripRoundParentheses,
  textHasParentheses,
  pluralFragments,
} from "./parentheses.js";

let limits = null;
let modelsData = null;
let lastReport = null;
let lastJournalId = null;
let lastExportUrl = null;

const appLayout = document.getElementById("app-layout");
const formCollapseBtn = document.getElementById("form-collapse");
const formRailBtn = document.getElementById("form-rail");
const journalCollapseBtn = document.getElementById("journal-collapse");
const journalRailBtn = document.getElementById("journal-rail");
const journalCountEl = document.getElementById("journal-count");
const blocksContainer = document.getElementById("blocks-container");
const blockTemplate = document.getElementById("block-template");
const addBlockBtn = document.getElementById("add-block");
const blockCountEl = document.getElementById("block-count");
const form = document.getElementById("analyze-form");
const submitBtn = document.getElementById("submit-btn");
const formErrors = document.getElementById("form-errors");
const statusEl = document.getElementById("status");
const previewFrame = document.getElementById("preview-frame");
const previewReport = document.getElementById("preview-report");
const previewPane = document.getElementById("preview-pane");
const openTabBtn = document.getElementById("open-tab");
const closePreviewBtn = document.getElementById("close-preview");
const progressPanel = document.getElementById("progress-panel");
const progressBar = document.getElementById("progress-bar");
const progressPercent = document.getElementById("progress-percent");
const progressLabel = document.getElementById("progress-label");
const progressLog = document.getElementById("progress-log");
const progressTrack = document.querySelector(".progress-track");
const modelSelect = document.getElementById("model");
const modelHint = document.getElementById("model-hint");
const journalList = document.getElementById("journal-list");
const journalMatches = document.getElementById("journal-matches");
const journalRefreshBtn = document.getElementById("journal-refresh");
const journalDeleteDialog = document.getElementById("journal-delete-dialog");
const journalDeleteTitle = document.getElementById("journal-delete-title");
const journalDeleteCancel = document.getElementById("journal-delete-cancel");
const journalDeleteConfirm = document.getElementById("journal-delete-confirm");
const journalRenameDialog = document.getElementById("journal-rename-dialog");
const journalRenameForm = document.getElementById("journal-rename-form");
const journalRenameInput = document.getElementById("journal-rename-input");
const journalRenameCancel = document.getElementById("journal-rename-cancel");
const journalRenameSave = document.getElementById("journal-rename-save");
const costBadge = document.getElementById("cost-badge");
const costHelpBtn = document.getElementById("cost-help-btn");
const costHelpDialog = document.getElementById("cost-help-dialog");
const costHelpClose = document.getElementById("cost-help-close");
const costHelpList = document.getElementById("cost-help-list");
const costHelpTotal = document.getElementById("cost-help-total");
const parensDialog = document.getElementById("parens-dialog");
const parensDialogLead = document.getElementById("parens-dialog-lead");
const parensPreview = document.getElementById("parens-preview");
const parensRemoveBtn = document.getElementById("parens-remove");
const parensKeepBtn = document.getElementById("parens-keep");
const parensCancelBtn = document.getElementById("parens-cancel");

/** Максимум чипов-примеров скобок в диалоге (остальное — «ещё N»). */
const PARENS_PREVIEW_CHIP_LIMIT = 14;

let matchDebounce = null;
let estimateDebounce = null;
let lastEstimate = null;
/** Запись журнала, ожидающая подтверждения удаления в диалоге. */
let pendingDeleteEntry = null;
/** Запись журнала для диалога переименования. */
let pendingRenameEntry = null;
/** Payload анализа, ожидающий выбора по скобкам. */
let pendingAnalysisPayload = null;
/** Идёт ли анализ с формы (блокирует загрузку снимка из журнала). */
let rerunInProgress = false;

/** Иконки действий в карточке журнала (только SVG, без подписей). */
const JOURNAL_ICON_RERUN =
  '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
  '<path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 3.5V8h-4.5" ' +
  'stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/></svg>';

const JOURNAL_ICON_OPEN =
  '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
  '<path d="M6.5 3.5H3.75A1.25 1.25 0 0 0 2.5 4.75v7.5A1.25 1.25 0 0 0 3.75 13.5h7.5a1.25 1.25 0 0 0 1.25-1.25V9.5M9 2.5h4.5V7M7.5 8.5 12.5 3.5" ' +
  'stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/></svg>';

const JOURNAL_ICON_RENAME =
  '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
  '<path d="M11.5 2.5a1.77 1.77 0 0 1 2.5 2.5L5.75 13.25 2.5 14l.75-3.25L11.5 2.5Z" ' +
  'stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/></svg>';

const JOURNAL_ICON_DELETE =
  '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
  '<path d="M2.5 4.5h11M6 4.5V3.25A.75.75 0 0 1 6.75 2.5h2.5a.75.75 0 0 1 .75.75V4.5M6.25 7v4.5M9.75 7v4.5M4 4.5l.5 8.25A1.25 1.25 0 0 0 5.75 14h4.5a1.25 1.25 0 0 0 1.25-1.25L12 4.5" ' +
  'stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/></svg>';

const WORD_RE = /[A-Za-zА-Яа-яЁё0-9]+(?:['’ʼ][A-Za-zА-Яа-яЁё0-9]+)?/gu;

// --- Сворачивание боковых панелей ---

/** Левая панель: свёрнута / развёрнута. */
function setFormCollapsed(collapsed) {
  appLayout.classList.toggle("is-form-collapsed", collapsed);
  formCollapseBtn?.setAttribute("aria-expanded", String(!collapsed));
  formRailBtn?.setAttribute("aria-expanded", String(!collapsed));
  if (formRailBtn) formRailBtn.hidden = !collapsed;
  formCollapseBtn?.setAttribute("title", collapsed ? "" : "Скрыть панель ввода");
  formCollapseBtn?.setAttribute("aria-label", collapsed ? "" : "Скрыть панель ввода");
}

/** Правая панель журнала: свёрнута / развёрнута. */
function setJournalCollapsed(collapsed) {
  appLayout.classList.toggle("is-journal-collapsed", collapsed);
  journalCollapseBtn?.setAttribute("aria-expanded", String(!collapsed));
  journalRailBtn?.setAttribute("aria-expanded", String(!collapsed));
  if (journalRailBtn) journalRailBtn.hidden = !collapsed;
  journalCollapseBtn?.setAttribute("title", collapsed ? "" : "Скрыть журнал");
  journalCollapseBtn?.setAttribute("aria-label", collapsed ? "" : "Скрыть журнал");
}

function toggleFormPanel() {
  setFormCollapsed(!appLayout.classList.contains("is-form-collapsed"));
  trackEvent("panel_toggle", { panel: "form", collapsed: appLayout.classList.contains("is-form-collapsed") });
}

function toggleJournalPanel() {
  setJournalCollapsed(!appLayout.classList.contains("is-journal-collapsed"));
  trackEvent("panel_toggle", { panel: "journal", collapsed: appLayout.classList.contains("is-journal-collapsed") });
}

formCollapseBtn?.addEventListener("click", toggleFormPanel);
formRailBtn?.addEventListener("click", toggleFormPanel);
journalCollapseBtn?.addEventListener("click", toggleJournalPanel);
journalRailBtn?.addEventListener("click", toggleJournalPanel);

// --- Загрузка конфигурации с бэкенда ---
function populateModelSelect(selectEl, selectedId) {
  selectEl.innerHTML = "";
  const groups = new Map();
  for (const m of modelsData.models) {
    if (!m.available) continue;
    const label = m.provider_label || m.provider;
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(m);
  }
  for (const [groupLabel, items] of groups) {
    const og = document.createElement("optgroup");
    og.label = groupLabel;
    for (const m of items) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.is_default ? `${m.id} (по умолчанию)` : m.id;
      opt.title = m.description;
      opt.dataset.provider = m.provider;
      if (m.id === selectedId) opt.selected = true;
      og.appendChild(opt);
    }
    selectEl.appendChild(og);
  }
}

async function loadLimits() {
  const res = await fetch("/api/limits");
  limits = await res.json();
  updateBlockCountHint();
}

async function loadModels() {
  const res = await fetch("/api/models");
  modelsData = await res.json();
  populateModelSelect(modelSelect, modelsData.default);

  if (!modelSelect.options.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Нет моделей — добавьте ключ в .env";
    modelSelect.appendChild(opt);
    submitBtn.disabled = true;
  }

  updateModelHint();
  scheduleCostEstimate();
}

function updateModelHint() {
  const id = modelSelect.value;
  const m = modelsData?.models.find((x) => x.id === id);
  if (!m) {
    modelHint.textContent = "";
    return;
  }
  const prov = m.provider_label ? `${m.provider_label} · ` : "";
  modelHint.textContent = `${prov}${m.description ?? ""}`;
}

modelSelect.addEventListener("change", () => {
  updateModelHint();
  scheduleCostEstimate();
});

document.getElementById("lang").addEventListener("change", scheduleCostEstimate);

// --- Счётчики блоков ---
function countWords(text) {
  return (text.match(WORD_RE) || []).length;
}

function countLines(text) {
  return text.split("\n").filter((l) => l.trim()).length;
}

function blockMetrics(text) {
  return { lines: countLines(text), words: countWords(text), chars: text.length };
}

function updateBlockCountHint() {
  const n = blocksContainer.querySelectorAll("[data-block]").length;
  const max = limits?.max_blocks ?? 5;
  blockCountEl.textContent = `${n} / ${max} блоков`;
  addBlockBtn.disabled = n >= max;
}

function createBlock(kind = "verse", text = "", title = "") {
  const frag = blockTemplate.content.cloneNode(true);
  const card = frag.querySelector("[data-block]");
  const kindSelect = frag.querySelector(".block-kind");
  const titleInput = frag.querySelector(".block-title");
  const textarea = frag.querySelector(".block-text");
  const removeBtn = frag.querySelector(".remove-block");

  kindSelect.value = kind;
  titleInput.value = title;
  textarea.value = text;
  textarea.addEventListener("input", () => {
    refreshCounters(card);
    scheduleTextMatch();
    scheduleCostEstimate();
  });
  removeBtn.addEventListener("click", () => {
    if (blocksContainer.querySelectorAll("[data-block]").length <= 1) {
      showErrors(["нужен хотя бы один блок"]);
      return;
    }
    card.remove();
    updateBlockCountHint();
    validateForm();
    scheduleCostEstimate();
  });

  blocksContainer.appendChild(frag);
  refreshCounters(card);
  updateBlockCountHint();
}

function refreshCounters(card) {
  if (!limits) return;
  const text = card.querySelector(".block-text").value;
  const m = blockMetrics(text);
  const isEmpty = !text.trim();
  let over = false;
  for (const [key, val, max] of [
    ["lines", m.lines, limits.max_lines],
    ["words", m.words, limits.max_words],
    ["chars", m.chars, limits.max_chars],
  ]) {
    const el = card.querySelector(`[data-metric="${key}"]`);
    el.querySelector("b").textContent = String(val);
    const isOver = !isEmpty && val > max;
    el.classList.toggle("over", isOver);
    if (isOver) over = true;
  }
  card.classList.toggle("over-limit", over);
  validateForm();
}

function collectBlocks() {
  return [...blocksContainer.querySelectorAll("[data-block]")].map((card) => ({
    kind: card.querySelector(".block-kind").value,
    title: card.querySelector(".block-title").value.trim() || null,
    text: card.querySelector(".block-text").value,
  }));
}

function filledBlocks() {
  return collectBlocks().filter((b) => b.text.trim());
}

function validateForm() {
  hideErrors();
  if (!limits) return false;
  const blocks = filledBlocks();
  const errors = [];
  if (!document.getElementById("song").value.trim()) errors.push("укажите название песни");
  if (blocks.length === 0) errors.push("заполните хотя бы один блок текста");
  blocks.forEach((b, i) => {
    const label = b.title || `блок ${i + 1}`;
    const m = blockMetrics(b.text);
    if (m.lines > limits.max_lines) errors.push(`${label}: слишком много строк (${m.lines}/${limits.max_lines})`);
    if (m.words > limits.max_words) errors.push(`${label}: слишком много слов (${m.words}/${limits.max_words})`);
    if (m.chars > limits.max_chars) errors.push(`${label}: слишком много символов (${m.chars}/${limits.max_chars})`);
  });
  const hasOver = [...blocksContainer.querySelectorAll(".over-limit")].some(
    (c) => c.querySelector(".block-text").value.trim()
  );
  submitBtn.disabled = errors.length > 0 || hasOver;
  return errors.length === 0;
}

const ERROR_INTROS = {
  input: "Проверьте ввод:",
  llm_validation: "Модель не смогла согласовать рифмы с текстом:",
  config: "Проблема с настройкой сервера:",
  server: "Ошибка сервера:",
};

function showErrors(messages, kind = "input") {
  formErrors.hidden = false;
  formErrors.innerHTML = `<p class="error-intro">${escapeHtml(ERROR_INTROS[kind] || "Ошибка:")}</p><ul>${messages.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`;
}

function hideErrors() {
  formErrors.hidden = true;
  formErrors.innerHTML = "";
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function setStatus(msg, loading = false) {
  statusEl.textContent = msg;
  statusEl.classList.toggle("loading", loading);
}

/** Показывает JSON-отчёт в превью (единый рендер для новых и legacy записей). */
function showPreview(report, { entryId = null, exportUrl = null } = {}) {
  lastReport = report;
  lastJournalId = entryId;
  lastExportUrl = exportUrl;
  previewPane.classList.remove("is-empty", "is-legacy");
  previewPane.classList.add("has-report");
  openTabBtn.hidden = false;
  closePreviewBtn.hidden = false;
  previewFrame.hidden = true;
  previewReport.hidden = false;
  renderReport(previewReport, report);
  highlightJournalItem(entryId);
}

/** Пустое состояние превью (без отчёта). */
function clearPreview() {
  lastReport = null;
  lastJournalId = null;
  lastExportUrl = null;
  previewReport.innerHTML = "";
  previewFrame.removeAttribute("srcdoc");
  previewFrame.hidden = true;
  previewReport.hidden = true;
  previewPane.classList.remove("has-report", "is-legacy");
  previewPane.classList.add("is-empty");
  openTabBtn.hidden = true;
  closePreviewBtn.hidden = true;
  highlightJournalItem(null);
}

function highlightJournalItem(entryId) {
  journalList.querySelectorAll(".journal-item").forEach((li) => {
    li.classList.toggle("is-active", entryId != null && li.dataset.id === entryId);
  });
}

/** Загружает JSON (или legacy HTML→JSON на сервере) и рендерит превью. */
async function loadReportInPreview(dataUrl, entryId = null, exportUrl = null) {
  const res = await fetch(dataUrl);
  if (!res.ok) {
    showErrors(["не удалось загрузить отчёт из журнала"]);
    return;
  }
  const report = await res.json();
  showPreview(report, { entryId, exportUrl });
  setStatus("Открыт разбор из журнала");
  // При открытии из журнала — фокус на результат, ввод сворачиваем.
  setFormCollapsed(true);
}

// --- Журнал разборов ---

/** Открывает диалог подтверждения удаления записи. */
function openJournalDeleteDialog(entry) {
  pendingDeleteEntry = entry;
  journalDeleteTitle.textContent = entry.song;
  journalDeleteConfirm.disabled = false;
  journalDeleteDialog.showModal();
}

/** Закрывает диалог удаления без действий. */
function closeJournalDeleteDialog() {
  pendingDeleteEntry = null;
  journalDeleteDialog.close();
}

/** DELETE /api/journal/:id — убирает запись с диска и обновляет список. */
async function confirmJournalDelete() {
  if (!pendingDeleteEntry) return;
  trackEvent("journal_delete", { entry_id: pendingDeleteEntry.id, song: pendingDeleteEntry.song });
  const entry = pendingDeleteEntry;
  const itemEl = journalList.querySelector(`.journal-item[data-id="${entry.id}"]`);
  journalDeleteConfirm.disabled = true;
  if (itemEl) itemEl.classList.add("is-deleting");

  try {
    const res = await fetch(`/api/journal/${encodeURIComponent(entry.id)}`, { method: "DELETE" });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const msg = detail?.detail || "не удалось удалить запись из журнала";
      showErrors([typeof msg === "string" ? msg : "не удалось удалить запись из журнала"]);
      return;
    }

    closeJournalDeleteDialog();
    if (lastJournalId === entry.id) clearPreview();
    await loadJournal();
    await matchInputText();
    setStatus(`«${entry.song}» удалён из журнала`);
  } catch {
    showErrors(["сетевая ошибка при удалении записи"]);
  } finally {
    journalDeleteConfirm.disabled = false;
    if (itemEl) itemEl.classList.remove("is-deleting");
  }
}

/** Открывает диалог переименования записи. */
function openJournalRenameDialog(entry) {
  pendingRenameEntry = entry;
  journalRenameInput.value = entry.song;
  journalRenameSave.disabled = false;
  journalRenameDialog.showModal();
  queueMicrotask(() => {
    journalRenameInput.focus();
    journalRenameInput.select();
  });
}

/** Закрывает диалог переименования без сохранения. */
function closeJournalRenameDialog() {
  pendingRenameEntry = null;
  journalRenameDialog.close();
}

/** PATCH /api/journal/:id — сохраняет новое название. */
async function confirmJournalRename(e) {
  e.preventDefault();
  if (!pendingRenameEntry) return;
  trackEvent("journal_rename", { entry_id: pendingRenameEntry.id });

  const newSong = journalRenameInput.value.trim();
  if (!newSong) {
    journalRenameInput.focus();
    return;
  }

  const entry = pendingRenameEntry;
  journalRenameSave.disabled = true;

  try {
    const res = await fetch(`/api/journal/${encodeURIComponent(entry.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ song: newSong }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const msg = detail?.detail || "не удалось переименовать запись";
      showErrors([typeof msg === "string" ? msg : "не удалось переименовать запись"]);
      return;
    }

    closeJournalRenameDialog();
    if (lastJournalId === entry.id && lastReport) {
      lastReport.song = newSong;
      renderReport(previewReport, lastReport);
    }
    await loadJournal();
    await matchInputText();
    setStatus(`Запись переименована: «${newSong}»`);
  } catch {
    showErrors(["сетевая ошибка при переименовании"]);
  } finally {
    journalRenameSave.disabled = false;
  }
}

function renderJournalItem(entry) {
  const li = document.createElement("li");
  li.className = "journal-item";
  li.dataset.id = entry.id;
  const canRerun = Boolean(entry.can_rerun);
  const exportHref = entry.data_url
    ? `/api/journal/${encodeURIComponent(entry.id)}/export.html`
    : entry.report_url;
  li.innerHTML = `
    <div class="journal-item-head">
      <div class="journal-item-title-block">
        <button type="button" class="journal-title" title="Открыть в превью">${escapeHtml(entry.song)}</button>
        <time datetime="${escapeHtml(entry.created_at)}">${escapeHtml(entry.created_label)}</time>
      </div>
      <div class="journal-item-toolbar" role="toolbar" aria-label="Действия с разбором">
        <button
          type="button"
          class="journal-action journal-rerun"
          data-can-rerun="${canRerun ? "true" : "false"}"
          ${canRerun ? "" : "disabled"}
          title="${canRerun ? "Загрузить в форму" : "Снимок входа недоступен"}"
          aria-label="${canRerun ? "Загрузить текст и параметры в форму" : "Загрузка недоступна"}"
        >${JOURNAL_ICON_RERUN}</button>
        <a
          class="journal-action journal-open"
          href="${escapeHtml(exportHref)}"
          target="_blank"
          rel="noopener"
          title="Открыть в новой вкладке"
          aria-label="Открыть в новой вкладке"
        >${JOURNAL_ICON_OPEN}</a>
        <button
          type="button"
          class="journal-action journal-rename"
          title="Переименовать"
          aria-label="Переименовать «${escapeHtml(entry.song)}»"
        >${JOURNAL_ICON_RENAME}</button>
        <button
          type="button"
          class="journal-action journal-delete journal-action--danger"
          title="Удалить"
          aria-label="Удалить «${escapeHtml(entry.song)}»"
        >${JOURNAL_ICON_DELETE}</button>
      </div>
    </div>
    <p class="journal-item-preview">${escapeHtml(entry.text_preview)}</p>
    <div class="journal-item-meta">${entry.chains} цепочек · ${entry.lines} строк · ${escapeHtml(entry.model)}</div>
  `;
  li.querySelector(".journal-title").addEventListener("click", () => {
    trackEvent("journal_view", { entry_id: entry.id, song: entry.song });
    loadReportInPreview(entry.data_url, entry.id, `/api/journal/${entry.id}/export.html`);
  });
  li.querySelector(".journal-delete").addEventListener("click", (e) => {
    e.stopPropagation();
    openJournalDeleteDialog(entry);
  });
  li.querySelector(".journal-rename").addEventListener("click", (e) => {
    e.stopPropagation();
    openJournalRenameDialog(entry);
  });
  li.querySelector(".journal-rerun").addEventListener("click", (e) => {
    e.stopPropagation();
    trackEvent("journal_load_to_form", { entry_id: entry.id });
    loadJournalInputIntoForm(entry);
  });
  li.querySelector(".journal-open").addEventListener("click", (e) => {
    e.stopPropagation();
    trackEvent("journal_export_tab", { entry_id: entry.id });
  });
  return li;
}

/** Блокирует форму и кнопки загрузки из журнала, пока идёт анализ. */
function setAnalysisBusy(busy) {
  rerunInProgress = busy;
  submitBtn.disabled = busy;
  addBlockBtn.disabled = busy;
  journalList.querySelectorAll(".journal-rerun").forEach((btn) => {
    const allowed = btn.dataset.canRerun === "true";
    btn.disabled = busy || !allowed;
    btn.classList.remove("is-loading");
  });
}

/** Общая обработка успешного анализа с формы. */
async function handleAnalysisSuccess(result) {
  trackEvent("analysis_success", {
    entry_id: result.journal?.id,
    model: result.meta?.model,
    chains: result.meta?.chains,
  });
  showPreview(result.report, {
    entryId: result.journal?.id,
    exportUrl: result.journal?.id ? `/api/journal/${result.journal.id}/export.html` : null,
  });
  const { chains, lines, model } = result.meta;
  const saved = result.journal ? " · сохранено в журнал" : "";
  setStatus(`Готово: ${chains} цепочек · ${lines} строк · ${model}${saved}`);
  setFormCollapsed(true);
  await loadJournal();
  await matchInputText();
}

/** Общая обработка ошибки анализа. */
function handleAnalysisFailure(err) {
  trackEvent("analysis_error", { kind: err.kind, errors: err.errors?.length || 0 });
  if (err.kind) {
    showErrors(err.errors, err.kind);
    setStatus(err.kind === "llm_validation" ? "Анализ не удался" : "");
  } else {
    showErrors([`сеть: ${err.message}`]);
    setStatus("");
  }
}

/** Подставляет в форму снимок входа из журнала (без автозапуска анализа). */
async function loadJournalInputIntoForm(entry) {
  if (rerunInProgress || !entry.can_rerun) return;

  const itemEl = journalList.querySelector(`.journal-item[data-id="${entry.id}"]`);
  const loadBtn = itemEl?.querySelector(".journal-rerun") || null;
  hideErrors();

  if (loadBtn) {
    loadBtn.disabled = true;
    loadBtn.classList.add("is-loading");
  }

  try {
    const res = await fetch(`/api/journal/${encodeURIComponent(entry.id)}/input`);
    if (!res.ok) {
      showErrors(["не удалось загрузить снимок входа"]);
      return;
    }

    const input = await res.json();
    applyJournalInputSnapshot(input);
    setFormCollapsed(false);
    setStatus(
      `«${input.song}» загружено в форму — смените модель или текст и нажмите «Разобрать рифмы»`,
    );
    document.getElementById("song").focus();
  } catch {
    showErrors(["сетевая ошибка при загрузке снимка"]);
  } finally {
    if (loadBtn) {
      loadBtn.classList.remove("is-loading");
      loadBtn.disabled = false;
    }
  }
}

/** Заполняет поля формы данными из GET /api/journal/{id}/input. */
function applyJournalInputSnapshot(input) {
  document.getElementById("song").value = input.song || "";

  const langSelect = document.getElementById("lang");
  if ([...langSelect.options].some((o) => o.value === input.lang)) {
    langSelect.value = input.lang;
  }

  if (input.model && [...modelSelect.options].some((o) => o.value === input.model)) {
    modelSelect.value = input.model;
    updateModelHint();
  }

  blocksContainer.innerHTML = "";
  const blocks = Array.isArray(input.blocks) ? input.blocks : [];
  if (blocks.length) {
    for (const block of blocks) {
      createBlock(block.kind || "verse", block.text || "", block.title || "");
    }
  } else {
    createBlock("verse");
  }

  updateBlockCountHint();
  validateForm();
  scheduleTextMatch();
  scheduleCostEstimate();

  const formScroll = document.querySelector("#form-panel .sidebar__scroll");
  if (formScroll) formScroll.scrollTop = 0;
}

async function loadJournal() {
  const res = await fetch("/api/journal");
  if (!res.ok) return;
  const data = await res.json();
  journalList.innerHTML = "";
  const total = data.entries?.length ?? 0;
  if (journalCountEl) {
    const n = total;
    const word = n === 1 ? "запись" : n >= 2 && n <= 4 ? "записи" : "записей";
    journalCountEl.textContent = total ? `${n} ${word}` : "Пока пусто";
  }
  if (!data.entries?.length) {
    journalList.innerHTML = '<li class="journal-empty hint">Пока нет сохранённых разборов.</li>';
    return;
  }
  for (const entry of data.entries) {
    journalList.appendChild(renderJournalItem(entry));
  }
  highlightJournalItem(lastJournalId);
}

function renderMatches(matches) {
  if (!matches.length) {
    journalMatches.hidden = true;
    journalMatches.innerHTML = "";
    return;
  }
  journalMatches.hidden = false;
  const links = matches
    .map(
      (m) =>
        `<button type="button" class="journal-match-link" data-id="${escapeHtml(m.id)}" data-data="${escapeHtml(m.data_url)}">${escapeHtml(m.song)}</button> (${escapeHtml(m.created_label)})`
    )
    .join(", ");
  journalMatches.innerHTML = `<strong>Этот текст уже разбирали:</strong> ${links}`;
  journalMatches.querySelectorAll(".journal-match-link").forEach((btn) => {
    btn.addEventListener("click", () => {
      loadReportInPreview(btn.dataset.data, btn.dataset.id, `/api/journal/${btn.dataset.id}/export.html`);
    });
  });
}

async function matchInputText() {
  const blocks = filledBlocks();
  if (!blocks.length) {
    renderMatches([]);
    return;
  }
  try {
    const res = await fetch("/api/journal/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blocks }),
    });
    if (!res.ok) return;
    const data = await res.json();
    renderMatches(data.matches || []);
  } catch {
    /* тихо */
  }
}

function scheduleTextMatch() {
  clearTimeout(matchDebounce);
  matchDebounce = setTimeout(matchInputText, 450);
}

journalRefreshBtn.addEventListener("click", () => loadJournal());

journalDeleteCancel.addEventListener("click", closeJournalDeleteDialog);
journalDeleteConfirm.addEventListener("click", () => confirmJournalDelete());
journalDeleteDialog.addEventListener("click", (e) => {
  if (e.target === journalDeleteDialog) closeJournalDeleteDialog();
});
journalDeleteDialog.addEventListener("cancel", (e) => {
  e.preventDefault();
  closeJournalDeleteDialog();
});

journalRenameCancel.addEventListener("click", closeJournalRenameDialog);
journalRenameForm.addEventListener("submit", confirmJournalRename);
journalRenameDialog.addEventListener("click", (e) => {
  if (e.target === journalRenameDialog) closeJournalRenameDialog();
});
journalRenameDialog.addEventListener("cancel", (e) => {
  e.preventDefault();
  closeJournalRenameDialog();
});

// --- Оценка стоимости LLM ---
function renderCostBadge(est) {
  lastEstimate = est;
  if (!est || est.api_calls === 0 || est.cost_usd_label === "—") {
    costBadge.hidden = true;
    costBadge.textContent = "";
    return;
  }
  costBadge.hidden = false;
  costBadge.textContent = est.cost_usd_label;
}

function renderCostHelpDialog(est) {
  if (!est || est.api_calls === 0) {
    costHelpTotal.textContent = "Заполните текст блока, чтобы увидеть оценку.";
    costHelpList.innerHTML = "";
    return;
  }
  costHelpTotal.textContent = `Примерно ${est.cost_usd_label} (${est.api_calls} запрос(ов) · ${est.total_tokens.toLocaleString("ru-RU")} токенов)`;
  costHelpList.innerHTML = est.breakdown
    .map(
      (item) =>
        `<li><strong>${escapeHtml(item.title)}</strong>${escapeHtml(item.detail)}</li>`
    )
    .join("");
}

async function fetchCostEstimate() {
  const blocks = filledBlocks();
  const payload = {
    lang: document.getElementById("lang").value,
    model: modelSelect.value,
    blocks: blocks.length ? blocks : [{ kind: "verse", text: " ", title: null }],
  };
  if (!blocks.length) {
    renderCostBadge(null);
    renderCostHelpDialog(null);
    return;
  }
  try {
    const res = await fetch("/api/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return;
    const est = await res.json();
    renderCostBadge(est);
    renderCostHelpDialog(est);
  } catch {
    /* тихо */
  }
}

function scheduleCostEstimate() {
  clearTimeout(estimateDebounce);
  estimateDebounce = setTimeout(fetchCostEstimate, 350);
}

costHelpBtn.addEventListener("click", () => {
  trackEvent("cost_help_open");
  if (lastEstimate) renderCostHelpDialog(lastEstimate);
  costHelpDialog.showModal();
});

costHelpClose.addEventListener("click", () => costHelpDialog.close());
costHelpDialog.addEventListener("click", (e) => {
  if (e.target === costHelpDialog) costHelpDialog.close();
});

// --- Прогресс-бар и лог ---
const STAGE_LABELS = {
  prepare: "Подготовка текста",
  phonetics: "Транскрипция IPA",
  llm: "Анализ рифм (LLM)",
  merge: "Слияние эвристик и LLM",
  annotate: "Разметка цепочек",
  render: "Сборка отчёта",
  done: "Готово",
};

function resetProgress() {
  progressPanel.hidden = false;
  progressBar.style.width = "0%";
  progressPercent.textContent = "0%";
  progressLabel.textContent = "Запуск…";
  progressTrack.setAttribute("aria-valuenow", "0");
  progressLog.innerHTML = "";
}

function appendProgressEntry(hint, log) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="plog-hint">${escapeHtml(hint)}</span><span class="plog-tech">${escapeHtml(log)}</span>`;
  progressLog.appendChild(li);
  progressLog.scrollTop = progressLog.scrollHeight;
}

function updateProgress(ev) {
  const pct = ev.percent ?? 0;
  progressBar.style.width = `${pct}%`;
  progressPercent.textContent = `${pct}%`;
  progressTrack.setAttribute("aria-valuenow", String(pct));
  progressLabel.textContent = STAGE_LABELS[ev.stage] || "Обработка…";
  if (ev.hint) appendProgressEntry(ev.hint, ev.log || "");
}

function hideProgress() {
  progressPanel.hidden = true;
}

// --- Скобки в тексте: диалог перед анализом ---

/** Рендер списка найденных фрагментов «(…)» по блокам. */
function renderParensPreview(hits) {
  parensPreview.innerHTML = "";
  let shown = 0;
  let total = 0;
  for (const hit of hits) total += hit.count;

  for (const hit of hits) {
    const li = document.createElement("li");
    li.className = "parens-preview-item";

    const label = document.createElement("span");
    label.className = "parens-preview-block";
    label.textContent = hit.label;
    li.appendChild(label);

    for (const seg of hit.segments) {
      if (shown >= PARENS_PREVIEW_CHIP_LIMIT) break;
      const chip = document.createElement("code");
      chip.className = "parens-chip";
      chip.textContent = seg;
      chip.title = seg;
      li.appendChild(chip);
      shown += 1;
    }
    parensPreview.appendChild(li);
    if (shown >= PARENS_PREVIEW_CHIP_LIMIT) break;
  }

  const rest = total - shown;
  if (rest > 0) {
    const more = document.createElement("li");
    more.className = "parens-preview-more";
    more.textContent = `…и ещё ${rest} ${pluralFragments(rest)}`;
    parensPreview.appendChild(more);
  }
}

/** Показывает диалог выбора: удалить скобки, оставить или отменить. */
function openParensDialog(hits) {
  const total = hits.reduce((sum, h) => sum + h.count, 0);
  const blocksWord = hits.length === 1 ? "блоке" : "блоках";
  parensDialogLead.textContent =
    `В ${blocksWord} найдено ${total} ${pluralFragments(total)} в круглых скобках. ` +
    "Удалить их из текста или оставить как слова для разбора?";
  renderParensPreview(hits);
  parensDialog.showModal();
}

/** Закрывает диалог скобок без запуска анализа. */
function closeParensDialog() {
  pendingAnalysisPayload = null;
  parensDialog.close();
}

/** Вырезает (…) из textarea всех блоков и обновляет счётчики. */
function applyParenthesesStripToForm() {
  blocksContainer.querySelectorAll("[data-block]").forEach((card) => {
    const textarea = card.querySelector(".block-text");
    if (!textHasParentheses(textarea.value)) return;
    textarea.value = stripRoundParentheses(textarea.value);
    refreshCounters(card);
  });
  validateForm();
  scheduleTextMatch();
  scheduleCostEstimate();
}

/** Запуск SSE-анализа (после проверки скобок). */
async function startAnalysis(payload) {
  hideErrors();
  setStatus("", true);
  setAnalysisBusy(true);

  try {
    const result = await analyzeWithProgress(payload);
    await handleAnalysisSuccess(result);
  } catch (err) {
    handleAnalysisFailure(err);
  } finally {
    setAnalysisBusy(false);
    validateForm();
    updateBlockCountHint();
  }
}

/** Обрабатывает выбор в диалоге скобок и при необходимости стартует анализ. */
async function proceedAfterParensChoice(removeParentheses) {
  const payload = pendingAnalysisPayload;
  pendingAnalysisPayload = null;
  parensDialog.close();
  if (!payload) return;

  if (removeParentheses) {
    trackEvent("parens_choice", { choice: "remove" });
    applyParenthesesStripToForm();
    if (!validateForm()) return;
    payload.blocks = filledBlocks();
    if (!payload.blocks.length) {
      showErrors(["после удаления скобок не осталось текста для разбора"]);
      return;
    }
  } else {
    trackEvent("parens_choice", { choice: "keep" });
  }

  await startAnalysis(payload);
}

parensRemoveBtn.addEventListener("click", () => proceedAfterParensChoice(true));
parensKeepBtn.addEventListener("click", () => proceedAfterParensChoice(false));
parensCancelBtn.addEventListener("click", closeParensDialog);
parensDialog.addEventListener("click", (e) => {
  if (e.target === parensDialog) closeParensDialog();
});
parensDialog.addEventListener("cancel", (e) => {
  e.preventDefault();
  closeParensDialog();
});

// --- SSE-поток анализа с формы ---
async function analyzeWithProgress(payload, streamUrl = "/api/analyze/stream") {
  resetProgress();
  const res = await fetch(streamUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok || !res.body) {
    let data = {};
    try {
      data = await res.json();
    } catch {
      /* ignore */
    }
    const detail = data.detail || {};
    throw { kind: detail.kind || "server", errors: detail.errors || ["ошибка сервера"] };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      const ev = JSON.parse(line.slice(6));

      if (ev.type === "progress") {
        updateProgress(ev);
      } else if (ev.type === "done") {
        updateProgress({ stage: "done", percent: 100, hint: "Отчёт готов.", log: "[pipeline] готово" });
        return ev;
      } else if (ev.type === "error") {
        throw { kind: ev.kind || "server", errors: ev.errors || ["неизвестная ошибка"] };
      }
    }
  }
  throw { kind: "server", errors: ["поток прервался без результата"] };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!validateForm()) return;

  const payload = {
    song: document.getElementById("song").value.trim(),
    lang: document.getElementById("lang").value,
    model: modelSelect.value,
    blocks: filledBlocks(),
  };

  trackEvent("form_submit", {
    lang: payload.lang,
    model: payload.model,
    block_count: payload.blocks.length,
  });

  const parenHits = scanBlocksForParentheses(payload.blocks);
  if (parenHits.length) {
    pendingAnalysisPayload = payload;
    openParensDialog(parenHits);
    return;
  }

  await startAnalysis(payload);
});

openTabBtn.addEventListener("click", () => {
  if (lastExportUrl) {
    window.open(lastExportUrl, "_blank");
    return;
  }
  if (!lastReport) return;
  const blob = new Blob([JSON.stringify(lastReport)], { type: "application/json" });
  window.open(URL.createObjectURL(blob), "_blank");
});

closePreviewBtn.addEventListener("click", () => {
  clearPreview();
  setStatus("");
});

addBlockBtn.addEventListener("click", () => {
  createBlock("verse");
  scheduleCostEstimate();
});
document.getElementById("song").addEventListener("input", validateForm);

async function init() {
  setJournalCollapsed(true);
  setFormCollapsed(false);
  if (formRailBtn) formRailBtn.hidden = true;
  if (journalRailBtn) journalRailBtn.hidden = false;
  initResizers();
  await Promise.all([loadLimits(), loadModels(), loadJournal()]);
  createBlock("verse");
  validateForm();
  scheduleCostEstimate();
}

init();
