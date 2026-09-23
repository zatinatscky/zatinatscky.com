/**
 * Детект и обработка круглых скобок в тексте блоков.
 * Служебные пометки в (…) часто не участвуют в рифме — пользователь решает сам.
 */

const KIND_LABELS = {
  verse: "Куплет",
  chorus: "Припев",
  hook: "Hook",
};

/** Все фрагменты вида «(…)» с учётом вложенности. */
export function extractParenthesisSegments(text) {
  const segments = [];
  let depth = 0;
  let start = -1;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === "(") {
      if (depth === 0) start = i;
      depth += 1;
    } else if (ch === ")" && depth > 0) {
      depth -= 1;
      if (depth === 0 && start >= 0) {
        segments.push(text.slice(start, i + 1));
        start = -1;
      }
    }
  }
  return segments;
}

/** Есть ли в тексте хотя бы одна пара круглых скобок. */
export function textHasParentheses(text) {
  return extractParenthesisSegments(text).length > 0;
}

/** Убирает всё внутри круглых скобок вместе со скобками. */
export function stripRoundParentheses(text) {
  let out = "";
  let depth = 0;

  for (const ch of text) {
    if (ch === "(") {
      depth += 1;
      continue;
    }
    if (ch === ")") {
      if (depth > 0) depth -= 1;
      continue;
    }
    if (depth === 0) out += ch;
  }
  return normalizeWhitespaceAfterStrip(out);
}

/** Убираем лишние пробелы после вырезания скобок. */
function normalizeWhitespaceAfterStrip(text) {
  const lines = text.split("\n").map((line) =>
    line
      .replace(/[ \t]{2,}/g, " ")
      .replace(/[ \t]+$/g, "")
      .replace(/^[ \t]+/g, "")
  );
  return lines.join("\n").replace(/\n{3,}/g, "\n\n");
}

/** Подпись блока для списка в диалоге. */
export function blockDisplayLabel(block, index) {
  const title = block.title?.trim();
  if (title) return title;
  const kind = KIND_LABELS[block.kind] || block.kind || "Блок";
  return `${kind} ${index + 1}`;
}

/**
 * Сканирует блоки формы: где есть скобки и какие фрагменты найдены.
 * @param {Array<{kind: string, title: string|null, text: string}>} blocks
 */
export function scanBlocksForParentheses(blocks) {
  const hits = [];
  blocks.forEach((block, blockIndex) => {
    const segments = extractParenthesisSegments(block.text);
    if (!segments.length) return;
    hits.push({
      blockIndex,
      label: blockDisplayLabel(block, blockIndex),
      segments,
      count: segments.length,
    });
  });
  return hits;
}

/** Склонение «фрагмент» для русского UI. */
export function pluralFragments(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "фрагмент";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "фрагмента";
  return "фрагментов";
}
