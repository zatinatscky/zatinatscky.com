/**
 * Загрузка реальных данных индексов из /api/indexes.
 *
 * Заменяет мок-генератор mock-data.js. Формат ответа специально повторяет то,
 * что раньше возвращал IVAN.genData(), поэтому app.js и charts.js работают с ним
 * без изменений:
 *
 *   { dates: Date[], btc: number[],
 *     indexes: [{ id, name, domain, sub, country, source, url,
 *                 unit, pre, dec, pct, gauge,
 *                 measures, method, behaviour, reading,
 *                 series: number[],
 *                 volume?: number[], volumeLabel?: string }] }
 *
 * Все ряды одной длины и выровнены по dates — этим занимается бэкенд
 * (indices/series.py, forward-fill).
 *
 * volume приходит только у индексов, привязанных к торгуемому рынку: оборот
 * биткоина под графиком доходности гособлигаций не значил бы ничего. Какой
 * индекс получает какой объём — см. indices/volumes.py.
 */
(function (global) {
  'use strict';

  var API_URL = '/api/indexes';

  /**
   * Даты приходят строками 'YYYY-MM-DD'. Разбираем как UTC-полдень, а не полночь:
   * при полуночи toLocaleDateString в отрицательных таймзонах показал бы
   * предыдущий день, и подписи на графике съехали бы на сутки.
   */
  function parseDay(iso) {
    var p = String(iso).split('-');
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2], 12, 0, 0));
  }

  /**
   * Тянет данные с бэкенда.
   * @param {number} days Глубина истории в днях (по умолчанию окно терминала).
   * @returns {Promise<Object>} данные в формате genData()
   */
  function loadData(days) {
    var url = API_URL + '?days=' + (days || 365);

    return fetch(url, { headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (payload) {
        if (!payload || !payload.dates || !payload.indexes || !payload.indexes.length) {
          throw new Error('Пустой ответ /api/indexes');
        }
        return {
          dates: payload.dates.map(parseDay),
          btc: payload.btc || [],
          indexes: payload.indexes,
          asOf: payload.asOf,
        };
      });
  }

  global.IVAN = global.IVAN || {};
  Object.assign(global.IVAN, {
    loadData: loadData,
    API_URL: API_URL,
  });
})(typeof window !== 'undefined' ? window : globalThis);
