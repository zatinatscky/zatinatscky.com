/**
 * Рендер JSON-отчёта в DOM превью.
 * Логика подсветки и hover совпадает с html_gen.py — UI обновляется для всех разборов.
 */

const MODE_LABELS = {
  llm: "OpenAI LLM",
  "llm-blocks": "OpenAI LLM (по блокам + IPA)",
  "llm-dual": "две модели LLM (union рифм)",
  cached: "кэш LLM",
  annotate: "ручной эталон",
  autodetect: "автодетектор",
};

const DEFAULT_PALETTE = {
  purple: "#b692f6",
  green: "#5fd08a",
  blue: "#6ba8f7",
  orange: "#f0a35e",
  pink: "#f178b6",
};

/** Экранирование текста для безопасной вставки в HTML. */
export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Форматирует ISO-дату для шапки отчёта. */
function formatGenerated(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, "0");
    const tz = -d.getTimezoneOffset();
    const sign = tz >= 0 ? "+" : "-";
    const ah = Math.floor(Math.abs(tz) / 60);
    const am = Math.abs(tz) % 60;
    const tzStr = `${sign}${pad(ah)}:${pad(am)}`;
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} (${tzStr})`;
  } catch {
    return iso;
  }
}

/** HEX цвет цепочки по id. */
function chainColor(chainId, chainsById, palette) {
  if (!chainId) return null;
  const chain = chainsById[chainId];
  if (!chain) return null;
  return palette[chain.color] || "#cccccc";
}

/** id цепочек блока в порядке появления. */
function chainIdsInBlock(block) {
  const seen = [];
  for (const line of block.lines || []) {
    for (const tok of line.tokens || []) {
      if (tok.is_word && tok.chain && !seen.includes(tok.chain)) {
        seen.push(tok.chain);
      }
    }
  }
  return seen;
}

/** Первая буква первого слова строки — заглавная (оформление стиха). */
function capitalizeWordStart(word) {
  for (let i = 0; i < word.length; i += 1) {
    const ch = word[i];
    if (/[a-zA-Zа-яёА-ЯЁ]/.test(ch)) {
      const up = ch.toUpperCase();
      if (up !== ch) return word.slice(0, i) + up + word.slice(i + 1);
      return word;
    }
  }
  return word;
}

/** Собирает DOM-фрагмент токенов строки (текст или IPA). */
function renderTokenSegs(tokens, chainsById, palette, useIpa) {
  const frag = document.createDocumentFragment();
  let lineCapitalized = false;
  for (const tok of tokens || []) {
    let text = useIpa ? tok.ipa : tok.display;
    if (!useIpa && tok.is_word && !lineCapitalized) {
      text = capitalizeWordStart(tok.display);
      lineCapitalized = true;
    }
    if (tok.is_word && tok.chain) {
      const span = document.createElement("span");
      span.className = "w-chain" + (tok.internal ? " w-int" : "");
      span.dataset.chain = tok.chain;
      const cc = chainColor(tok.chain, chainsById, palette);
      if (cc) span.style.setProperty("--cc", cc);
      span.textContent = text;
      frag.appendChild(span);
    } else {
      frag.appendChild(document.createTextNode(text));
    }
  }
  return frag;
}

/** Hover и клик по чипам: подсветка цепочки в тексте. */
export function attachReportHover(root) {
  const textCard = root.querySelector("#rv-text-card") || root.querySelector(".rv-card");
  const table = root.querySelector("tbody");
  if (!textCard) return;

  let pinnedId = null;

  function setChipActive(id) {
    root.querySelectorAll(".rv-chip[data-chain]").forEach((chip) => {
      const on = id != null && chip.dataset.chain === id;
      chip.classList.toggle("rv-chip-active", on);
      chip.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function applyFocus(id, cc) {
    if (!id) {
      textCard.classList.remove("focus-chain");
      textCard.removeAttribute("data-active-chain");
      textCard.querySelectorAll(".w-chain").forEach((el) => el.classList.remove("chain-active"));
      if (table) {
        table.querySelectorAll("tr.chain-active").forEach((row) => {
          row.classList.remove("chain-active");
          row.style.removeProperty("--row-cc");
        });
      }
      setChipActive(null);
      return;
    }

    textCard.classList.add("focus-chain");
    textCard.setAttribute("data-active-chain", id);
    textCard.querySelectorAll(".w-chain").forEach((el) => {
      el.classList.toggle("chain-active", el.dataset.chain === id);
    });
    if (table) {
      table.querySelectorAll("tr[data-chain]").forEach((row) => {
        const on = row.dataset.chain === id;
        row.classList.toggle("chain-active", on);
        if (on && cc) row.style.setProperty("--row-cc", cc);
        else if (!on) row.style.removeProperty("--row-cc");
      });
    }
    setChipActive(id);
  }

  function focusChain(id, cc) {
    if (pinnedId) return;
    applyFocus(id, cc);
  }

  function pinChain(id, cc) {
    pinnedId = pinnedId === id ? null : id;
    applyFocus(pinnedId, cc);
    if (pinnedId) {
      const first = textCard.querySelector(".w-chain.chain-active");
      if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function unpin() {
    pinnedId = null;
    applyFocus(null);
  }

  function clearFocus() {
    if (pinnedId) return;
    applyFocus(null);
  }

  /** Клик вне чипа, слова цепочки и строки таблицы — снять закрепление. */
  function isChainControl(target) {
    return Boolean(target.closest(".rv-chip[data-chain], .w-chain, tr.rv-chain-row"));
  }

  root.querySelectorAll(".rv-chip[data-chain]").forEach((chip) => {
    chip.addEventListener("click", (e) => {
      e.preventDefault();
      pinChain(chip.dataset.chain, chip.style.getPropertyValue("--cc") || "");
    });
  });

  if (table) {
    table.querySelectorAll("tr[data-chain]").forEach((row) => {
      row.addEventListener("click", () => {
        pinChain(row.dataset.chain, row.style.getPropertyValue("--row-cc") || "");
      });
      row.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          pinChain(row.dataset.chain, row.style.getPropertyValue("--row-cc") || "");
        }
      });
    });
  }

  root.addEventListener("click", (e) => {
    if (!pinnedId) return;
    if (isChainControl(e.target)) return;
    unpin();
  });

  root.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && pinnedId) {
      e.preventDefault();
      unpin();
    }
  });

  textCard.addEventListener("mouseover", (e) => {
    const w = e.target.closest(".w-chain");
    if (!w) {
      if (!pinnedId) clearFocus();
      return;
    }
    if (pinnedId) return;
    const id = w.dataset.chain;
    if (textCard.getAttribute("data-active-chain") === id) return;
    focusChain(id, w.style.getPropertyValue("--cc") || "");
  });

  textCard.addEventListener("mouseleave", clearFocus);
}

/**
 * Рендерит полный отчёт в container.
 * @returns {HTMLElement} корневой .report-view
 */
export function renderReport(container, report) {
  const palette = { ...DEFAULT_PALETTE, ...(report.palette || {}) };
  const meta = report.meta || {};
  const chains = report.chains || [];
  const chainsById = Object.fromEntries(chains.map((c) => [c.id, c]));
  const counts = report.member_counts || {};
  const modeLabel = MODE_LABELS[meta.analysis_mode] || meta.analysis_mode || "—";

  const root = document.createElement("div");
  root.className = "report-view";

  // --- Шапка ---
  const h1 = document.createElement("h1");
  h1.textContent = report.song || "Без названия";
  root.appendChild(h1);

  const muted = document.createElement("p");
  muted.className = "rv-muted";
  muted.innerHTML = `Автоматический фонетический разбор рифм. Источник: <b>${escapeHtml(report.source || "—")}</b>`;
  root.appendChild(muted);

  const version = document.createElement("p");
  version.className = "rv-version";
  let verText = `Версия разбора: <b>${escapeHtml(formatGenerated(meta.generated_at))}</b> · режим: <b>${escapeHtml(modeLabel)}</b>`;
  if (meta.llm_model) verText += ` · модель: <b>${escapeHtml(meta.llm_model)}</b>`;
  if (report.imported_from === "html") {
    verText += ` · <span title="Конвертировано из legacy HTML">импорт HTML</span>`;
  }
  version.innerHTML = verText;
  root.appendChild(version);

  // --- Статистика ---
  const stats = document.createElement("div");
  stats.className = "rv-stats";
  const statItems = [
    [meta.chains ?? chains.length, "звуковые цепочки"],
    [meta.rhyme_words ?? Object.values(counts).reduce((a, b) => a + b, 0), "созвучных слов"],
    [meta.multi ?? 0, "многосложные"],
    [meta.internal ?? 0, "с внутр. рифмой"],
  ];
  for (const [val, label] of statItems) {
    const box = document.createElement("div");
    box.className = "rv-stat";
    box.innerHTML = `<div class="v">${escapeHtml(String(val))}</div><div class="l">${escapeHtml(label)}</div>`;
    stats.appendChild(box);
  }
  root.appendChild(stats);

  // --- Текст с подсветкой ---
  const textHead = document.createElement("div");
  textHead.className = "rv-text-head";

  const h2text = document.createElement("h2");
  h2text.textContent = "Текст с подсветкой и транскрипцией";
  textHead.appendChild(h2text);

  const ipaToggleLabel = document.createElement("label");
  ipaToggleLabel.className = "rv-ipa-toggle";
  const ipaCheckbox = document.createElement("input");
  ipaCheckbox.type = "checkbox";
  ipaCheckbox.className = "rv-ipa-toggle-input";
  ipaCheckbox.checked = true;
  ipaCheckbox.setAttribute("aria-controls", "rv-text-card");
  const savedIpa = localStorage.getItem("rhyme-ui-show-ipa");
  if (savedIpa === "0") {
    ipaCheckbox.checked = false;
    root.classList.add("ipa-collapsed");
  }
  ipaToggleLabel.append(ipaCheckbox, document.createTextNode(" Показать IPA"));
  textHead.appendChild(ipaToggleLabel);
  root.appendChild(textHead);

  const legend = document.createElement("div");
  legend.className = "rv-legend";
  legend.innerHTML =
    '<span>Цветная <b>подложка</b> = звуковая цепочка · наведите на слово или <b>нажмите чип / строку в таблице</b> · клик в пустое место или Esc — снять</span>' +
    '<span><span class="int">Слово</span> — внутренняя рифма (пунктир)</span>' +
    '<span class="rv-muted"><span class="rv-ipa-mark">↪</span> строка снизу — IPA</span>';
  root.appendChild(legend);

  const card = document.createElement("div");
  card.className = "rv-card";
  card.id = "rv-text-card";

  for (const block of report.blocks || []) {
    const sec = document.createElement("div");
    sec.className = "rv-section";

    const secTitle = document.createElement("div");
    secTitle.className = "rv-sec-title";
    secTitle.textContent = block.title || "Секция";
    sec.appendChild(secTitle);

    const chips = document.createElement("div");
    chips.className = "rv-chips";
    for (const cid of chainIdsInBlock(block)) {
      const chain = chainsById[cid];
      if (!chain) continue;
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "rv-chip";
      chip.dataset.chain = cid;
      chip.setAttribute("aria-pressed", "false");
      chip.title = chain.words;
      chip.style.setProperty("--cc", palette[chain.color] || "#ccc");
      chip.textContent = chain.sound;
      chips.appendChild(chip);
    }
    sec.appendChild(chips);

    for (const line of block.lines || []) {
      const lineEl = document.createElement("div");
      lineEl.className = "rv-line";

      const row1 = document.createElement("div");
      row1.className = "rv-lrow";
      const num1 = document.createElement("span");
      num1.className = "rv-num";
      num1.textContent = String(line.no);
      const textEl = document.createElement("span");
      textEl.className = "rv-text";
      textEl.appendChild(renderTokenSegs(line.tokens, chainsById, palette, false));
      row1.append(num1, textEl);

      const row2 = document.createElement("div");
      row2.className = "rv-lrow rv-ipa-row";
      const num2 = document.createElement("span");
      num2.className = "rv-num rv-ipa-mark";
      num2.textContent = "↪";
      num2.setAttribute("aria-hidden", "true");
      const ipaEl = document.createElement("span");
      ipaEl.className = "rv-ipa";
      ipaEl.appendChild(renderTokenSegs(line.tokens, chainsById, palette, true));
      row2.append(num2, ipaEl);

      lineEl.append(row1, row2);
      sec.appendChild(lineEl);
    }
    card.appendChild(sec);
  }
  root.appendChild(card);

  // --- Таблица цепочек ---
  const h2map = document.createElement("h2");
  h2map.textContent = "Карта звуковых цепочек";
  root.appendChild(h2map);

  const tableWrap = document.createElement("div");
  tableWrap.className = "rv-card";
  const table = document.createElement("table");
  table.innerHTML =
    "<thead><tr><th>Звук</th><th>Слова</th><th>Строки</th><th>Тип</th></tr></thead>";
  const tbody = document.createElement("tbody");
  for (const c of chains) {
    const tr = document.createElement("tr");
    tr.className = "rv-chain-row";
    tr.dataset.chain = c.id;
    tr.tabIndex = 0;
    tr.setAttribute("role", "button");
    tr.title = `Подсветить в тексте: ${c.words}`;
    const color = palette[c.color] || "#ccc";
    tr.style.setProperty("--row-cc", color);
    tr.innerHTML = `<td style="color:${color};font-weight:600">${escapeHtml(c.sound)}</td>` +
      `<td>${escapeHtml(c.words)}</td>` +
      `<td>${escapeHtml(c.lines)}</td>` +
      `<td>${escapeHtml(c.kind)}</td>`;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  root.appendChild(tableWrap);

  // --- Бар-чарт топ-цепочек (подписи данных у каждого бара) ---
  const h2chart = document.createElement("h2");
  h2chart.textContent = "Самые длинные цепочки (число созвучных слов)";
  root.appendChild(h2chart);

  const chart = document.createElement("div");
  chart.className = "rv-chart";
  const top = [...chains].sort((a, b) => (counts[b.id] || 0) - (counts[a.id] || 0)).slice(0, 6);
  const maxCount = Math.max(...top.map((c) => counts[c.id] || 0), 1);

  for (const c of top) {
    const cnt = counts[c.id] || 0;
    const color = palette[c.color] || "#ccc";
    const row = document.createElement("div");
    row.className = "rv-bar-row";

    const label = document.createElement("span");
    label.className = "rv-bar-label";
    label.style.color = color;
    label.textContent = c.sound;

    const track = document.createElement("span");
    track.className = "rv-bar-track";

    const fill = document.createElement("span");
    fill.className = "rv-bar-fill";
    fill.style.width = `${(cnt / maxCount) * 100}%`;
    fill.style.background = color;

    const value = document.createElement("span");
    value.className = "rv-bar-value";
    value.textContent = String(cnt);

    track.append(fill, value);
    row.append(label, track);
    chart.appendChild(row);
  }
  root.appendChild(chart);

  const chartNote = document.createElement("p");
  chartNote.className = "rv-muted";
  chartNote.style.fontSize = "0.78rem";
  chartNote.textContent = "Подписи (число слов) указаны справа от каждого бара.";
  root.appendChild(chartNote);

  container.innerHTML = "";
  container.appendChild(root);

  ipaCheckbox.addEventListener("change", () => {
    const show = ipaCheckbox.checked;
    root.classList.toggle("ipa-collapsed", !show);
    localStorage.setItem("rhyme-ui-show-ipa", show ? "1" : "0");
  });

  attachReportHover(root);
  return root;
}
