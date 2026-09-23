/**
 * Отправка событий поведения пользователя в БД (POST /api/events).
 * Пакетирует события и шлёт с небольшой задержкой, чтобы не спамить API.
 */

const _queue = [];
let _flushTimer = null;
const FLUSH_MS = 400;

/** Поставить событие в очередь. */
export function trackEvent(eventName, properties = {}) {
  _queue.push({
    event_name: eventName,
    properties,
    page_path: window.location.pathname || "/",
  });
  if (!_flushTimer) {
    _flushTimer = setTimeout(flushEvents, FLUSH_MS);
  }
}

/** Немедленно отправить накопленные события. */
export async function flushEvents() {
  if (_flushTimer) {
    clearTimeout(_flushTimer);
    _flushTimer = null;
  }
  if (!_queue.length) return;

  const batch = _queue.splice(0, 50);
  try {
    await fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    });
  } catch {
    /* аналитика не должна ломать UI */
  }
}

/** Перед закрытием вкладки — дослать очередь. */
window.addEventListener("pagehide", () => {
  if (!_queue.length) return;
  const batch = _queue.splice(0, 50);
  navigator.sendBeacon?.(
    "/api/events",
    new Blob([JSON.stringify({ events: batch })], { type: "application/json" })
  );
});
