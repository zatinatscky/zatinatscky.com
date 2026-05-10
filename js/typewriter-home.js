/**
 * Эффект «печати» на главной: фразы из JSON по очереди.
 * После полного набора фраза показывается ещё HOLD_AFTER_TYPING_MS, затем стирается;
 * следующая фраза набирается с нуля. Последняя фраза не стирается — курсор остаётся.
 * Резерв: один атрибут data-typewriter-text. Учитывается prefers-reduced-motion.
 */
(function () {
  /** Задержка между символами при наборе (мс) */
  var STEP_MS = 42;

  /**
   * Сколько держать полностью набранную фразу на экране перед очисткой,
   * если после неё есть ещё фразы (мс).
   */
  var HOLD_AFTER_TYPING_MS = 2000;

  /**
   * Собирает массив строк из JSON внутри баннера или из data-typewriter-text.
   * @param {HTMLElement} banner
   * @returns {string[]}
   */
  function getPhrases(banner) {
    var jsonEl = banner.querySelector("script.typewriter-phrases-json");
    if (jsonEl && jsonEl.textContent) {
      try {
        var parsed = JSON.parse(jsonEl.textContent.trim());
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed.map(function (s) {
            return String(s);
          });
        }
      } catch (e) {
        /* при ошибке разбора падаем на одиночную строку */
      }
    }
    var single = banner.getAttribute("data-typewriter-text");
    if (single) {
      return [single];
    }
    return [];
  }

  /**
   * Запускает цикл «набор → пауза → стирание» или полный текст при reduced motion.
   * @param {HTMLElement} banner
   */
  function runBanner(banner) {
    var phrases = getPhrases(banner);
    var out = banner.querySelector(".typewriter-output");
    var cursor = banner.querySelector(".typewriter-cursor");
    var a11y = banner.querySelector(".typewriter-a11y");

    if (!out || phrases.length === 0) {
      return;
    }

    var fullA11y = phrases.join("\n");
    if (a11y) {
      a11y.textContent = fullA11y;
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      out.textContent = fullA11y;
      if (cursor) {
        cursor.hidden = true;
      }
      return;
    }

    var phraseIdx = 0;
    var charIdx = 0;

    function finishCursor() {
      if (cursor) {
        cursor.classList.add("typewriter-cursor--done");
      }
    }

    /**
     * Один шаг: либо следующий символ текущей фразы, либо завершение фразы
     * (ожидание, стирание или финал на последней строке).
     */
    function tick() {
      if (phraseIdx >= phrases.length) {
        finishCursor();
        return;
      }

      var current = phrases[phraseIdx];

      if (charIdx < current.length) {
        out.textContent = current.slice(0, charIdx + 1);
        charIdx += 1;
        window.setTimeout(tick, STEP_MS);
        return;
      }

      /* Вся текущая фраза уже на экране */
      if (phraseIdx === phrases.length - 1) {
        finishCursor();
        return;
      }

      /* Не последняя: подождать, очистить и начать следующую */
      window.setTimeout(function () {
        out.textContent = "";
        phraseIdx += 1;
        charIdx = 0;
        tick();
      }, HOLD_AFTER_TYPING_MS);
    }

    tick();
  }

  function init() {
    document.querySelectorAll(".typewriter-banner").forEach(runBanner);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
