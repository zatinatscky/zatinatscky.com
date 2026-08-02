/**
 * Общие утилиты IVAN: форматирование, теги, зоны, тема, localStorage, навигация.
 */
(function (global) {
  'use strict';

  var LS_WATCH = 'ivan_watchlist';
  var LS_ALERTS = 'ivan_alerts';
  var LS_WELCOME = 'ivan_welcome_dismissed';
  var LS_SCROLL = 'ivan_home_scroll';

  function fmt(v, d) {
    return Number(v).toLocaleString('en-US', {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    });
  }

  function kfmt(n) {
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return '' + Math.round(n);
  }

  function fmtD(d) {
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function fmtDLong(d) {
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }

  function tagsOf(meta) {
    var t = [meta.domain || 'Crypto', meta.sub || meta.cat];
    if (meta.country) t.push(meta.country);
    return t;
  }

  function fmtChange(meta, cur, prev) {
    if (meta.pct) {
      var p = (cur / prev - 1) * 100;
      return { txt: (p >= 0 ? '+' : '') + p.toFixed(2) + '%', up: p >= 0 };
    }
    var dd = cur - prev;
    return {
      txt: (dd >= 0 ? '+' : '') + dd.toFixed(meta.dec),
      up: dd >= 0,
    };
  }

  function valStr(meta, v) {
    return (meta.pre || '') + fmt(v, meta.dec) + (meta.unit || '');
  }

  function fngZone(v) {
    if (v < 25) return { label: 'Extreme Fear', color: '#c05b3d' };
    if (v < 48) return { label: 'Fear', color: '#cf8a58' };
    if (v < 53) return { label: 'Neutral', color: '#b3a26b' };
    if (v < 75) return { label: 'Greed', color: '#5d9c85' };
    return { label: 'Extreme Greed', color: '#2f8268' };
  }

  function zoneOf(meta, v) {
    if (meta.id === 'fng') return fngZone(v);
    if (meta.id === 'altseason') {
      if (v < 25) return { label: 'Bitcoin Season', color: '#cf8a58' };
      if (v > 75) return { label: 'Altcoin Season', color: '#2f8268' };
      return { label: 'Transition', color: '#b3a26b' };
    }
    if (meta.gauge) return fngZone(v);
    var s = meta.series;
    var below = s.filter(function (x) {
      return x <= v;
    }).length;
    var pct = (below / s.length) * 100;
    if (pct >= 82)
      return { label: 'Very high vs 52w', color: 'var(--accent-strong)' };
    if (pct >= 60) return { label: 'High vs 52w', color: 'var(--text-dim)' };
    if (pct >= 40) return { label: 'Mid vs 52w', color: 'var(--text-dim)' };
    if (pct >= 18) return { label: 'Low vs 52w', color: 'var(--text-dim)' };
    return { label: 'Very low vs 52w', color: 'var(--accent-strong)' };
  }

  function hexA(h, a) {
    h = (h || '#DDBA9B').replace('#', '');
    if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
    var n = parseInt(h, 16);
    return (
      'rgba(' +
      ((n >> 16) & 255) +
      ',' +
      ((n >> 8) & 255) +
      ',' +
      (n & 255) +
      ',' +
      a +
      ')'
    );
  }

  /** CSS-переменные темы (light/dark + accent) */
  function themeVars(theme, accentOverride) {
    var dark = theme === 'dark';
    var accent =
      accentOverride || (dark ? '#DDBA9B' : '#013547');
    var v = dark
      ? {
          bg: '#022733',
          bg2: '#013547',
          hairline: 'rgba(235,235,235,.12)',
          borderS: 'rgba(235,235,235,.28)',
          layer: 'rgba(235,235,235,.07)',
          text: '#EBEBEB',
          dim: '#D0D8DF',
          faint: '#7fa0ac',
          grid: 'rgba(235,235,235,.08)',
          up: '#6fbf9a',
          down: '#e08a70',
          band: '#DDBA9B',
          bandText: '#013547',
          bandDim: '#6d5137',
          bandLine: 'rgba(1,53,71,.18)',
          bandUp: '#1e6b4e',
          bandDown: '#a34a2e',
          tone: '#DDBA9B',
          toneSoft: 'rgba(221,186,155,.4)',
          shadow: 'rgba(0,10,15,.5)',
          accentStrong: '#DDBA9B',
        }
      : {
          bg: '#EBEBEB',
          bg2: '#F7F6F4',
          hairline: 'rgba(1,53,71,.13)',
          borderS: 'rgba(1,53,71,.3)',
          layer: 'rgba(1,53,71,.05)',
          text: '#013547',
          dim: '#6C6F6E',
          faint: '#8b9aa0',
          grid: 'rgba(1,53,71,.08)',
          up: '#2e7d5f',
          down: '#bf5b41',
          band: '#013547',
          bandText: '#EBEBEB',
          bandDim: '#9db3bc',
          bandLine: 'rgba(235,235,235,.14)',
          bandUp: '#8fd4b4',
          bandDown: '#f0a48a',
          tone: '#DDBA9B',
          toneSoft: 'rgba(221,186,155,.55)',
          shadow: 'rgba(1,53,71,.16)',
          accentStrong: '#013547',
        };
    v.accent = accent;
    v.accentSoft = hexA(accent, 0.14);
    v.upSoft = hexA(v.up, 0.13);
    var hh = accent.replace('#', '');
    var n = parseInt(
      hh.length === 3
        ? hh
            .split('')
            .map(function (c) {
              return c + c;
            })
            .join('')
        : hh,
      16
    );
    var lum =
      0.299 * ((n >> 16) & 255) +
      0.587 * ((n >> 8) & 255) +
      0.114 * (n & 255);
    v.onAccent = lum > 150 ? '#013547' : '#EBEBEB';
    return v;
  }

  function rootStyleCss(theme, accent) {
    var v = themeVars(theme, accent);
    return (
      '--bg:' +
      v.bg +
      ';--bg2:' +
      v.bg2 +
      ';--hairline:' +
      v.hairline +
      ';--border-s:' +
      v.borderS +
      ';--layer:' +
      v.layer +
      ';--text:' +
      v.text +
      ';--text-dim:' +
      v.dim +
      ';--text-faint:' +
      v.faint +
      ';--grid:' +
      v.grid +
      ';--up:' +
      v.up +
      ';--up-soft:' +
      v.upSoft +
      ';--down:' +
      v.down +
      ';--accent:' +
      v.accent +
      ';--accent-soft:' +
      v.accentSoft +
      ';--accent-strong:' +
      v.accentStrong +
      ';--on-accent:' +
      v.onAccent +
      ';--band:' +
      v.band +
      ';--band-text:' +
      v.bandText +
      ';--band-dim:' +
      v.bandDim +
      ';--band-line:' +
      v.bandLine +
      ';--band-up:' +
      v.bandUp +
      ';--band-down:' +
      v.bandDown +
      ';--tone:' +
      v.tone +
      ';--tone-soft:' +
      v.toneSoft +
      ';--shadow:' +
      v.shadow +
      ';display:flex;align-items:stretch;min-height:100vh;background:var(--bg);color:var(--text);font-family:\'Archivo\',system-ui,sans-serif;transition:background .25s,color .25s;'
    );
  }

  function loadWatchlist() {
    try {
      var w = JSON.parse(localStorage.getItem(LS_WATCH) || '[]');
      return Array.isArray(w) ? w : [];
    } catch (e) {
      return [];
    }
  }

  function saveWatchlist(w) {
    try {
      localStorage.setItem(LS_WATCH, JSON.stringify(w));
    } catch (e) {}
  }

  function loadAlerts() {
    try {
      var a = JSON.parse(localStorage.getItem(LS_ALERTS) || '{}');
      return a && typeof a === 'object' ? a : {};
    } catch (e) {
      return {};
    }
  }

  function saveAlerts(a) {
    try {
      localStorage.setItem(LS_ALERTS, JSON.stringify(a));
    } catch (e) {}
  }

  function isWelcomeDismissed() {
    try {
      return localStorage.getItem(LS_WELCOME) === '1';
    } catch (e) {
      return false;
    }
  }

  function setWelcomeDismissed() {
    try {
      localStorage.setItem(LS_WELCOME, '1');
    } catch (e) {}
  }

  /**
   * URL главной: в проде это `/` (Host = ivan.*).
   * Локально можно открыть `/ivan/home.html` без Host — запоминаем путь возврата.
   */
  var LS_HOME = 'ivan_home_url';

  function homeUrl() {
    try {
      var saved = sessionStorage.getItem(LS_HOME);
      if (saved) return saved;
    } catch (e) {}
    // Если сейчас смотрим статику /ivan/* — возвращаемся туда же.
    if (location.pathname.indexOf('/ivan/') === 0) return '/ivan/home.html';
    return '/';
  }

  /** Переход на страницу индекса с сохранением scroll и URL home */
  function navigateToIndex(id) {
    try {
      sessionStorage.setItem(LS_SCROLL, String(window.scrollY));
      // Запоминаем, откуда ушли ( /  или /ivan/home.html ).
      if (document.body && document.body.dataset.page === 'home') {
        sessionStorage.setItem(
          LS_HOME,
          location.pathname.indexOf('/ivan/') === 0 ? '/ivan/home.html' : '/'
        );
      }
    } catch (e) {}
    window.location.href = '/i/' + encodeURIComponent(id);
  }

  function goHome() {
    window.location.href = homeUrl();
  }

  function restoreHomeScroll() {
    try {
      var y = parseInt(sessionStorage.getItem(LS_SCROLL) || '0', 10);
      if (y > 0) {
        requestAnimationFrame(function () {
          window.scrollTo(0, y);
        });
      }
    } catch (e) {}
  }

  function relChg(m) {
    var s = m.series;
    var p = s[s.length - 2];
    return (s[s.length - 1] - p) / Math.abs(p || 1);
  }

  function rangePos(m) {
    var s = m.series;
    var c = s[s.length - 1];
    return (
      s.filter(function (x) {
        return x <= c;
      }).length / s.length
    );
  }

  function alertTriggered(meta, a) {
    if (!a) return false;
    var cur = meta.series[meta.series.length - 1];
    return a.op === 'below' ? cur < a.value : cur > a.value;
  }

  global.IVAN = global.IVAN || {};
  Object.assign(global.IVAN, {
    fmt: fmt,
    kfmt: kfmt,
    fmtD: fmtD,
    fmtDLong: fmtDLong,
    tagsOf: tagsOf,
    fmtChange: fmtChange,
    valStr: valStr,
    zoneOf: zoneOf,
    fngZone: fngZone,
    themeVars: themeVars,
    rootStyleCss: rootStyleCss,
    loadWatchlist: loadWatchlist,
    saveWatchlist: saveWatchlist,
    loadAlerts: loadAlerts,
    saveAlerts: saveAlerts,
    isWelcomeDismissed: isWelcomeDismissed,
    setWelcomeDismissed: setWelcomeDismissed,
    navigateToIndex: navigateToIndex,
    goHome: goHome,
    restoreHomeScroll: restoreHomeScroll,
    relChg: relChg,
    rangePos: rangePos,
    alertTriggered: alertTriggered,
    LS_SCROLL: LS_SCROLL,
  });
})(typeof window !== 'undefined' ? window : globalThis);
