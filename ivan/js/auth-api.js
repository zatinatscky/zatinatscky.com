/**
 * Клиент авторизации IVAN Terminal.
 *
 * Провайдеры: Google (редирект) и Telegram Login Widget (POST JSON).
 * Сессия — HttpOnly cookie; фронт только читает /api/me и дергает watchlist API.
 * До логина watchlist остаётся в localStorage; после — merge + PUT на сервер.
 */
(function (global) {
  'use strict';

  function jsonFetch(url, opts) {
    var o = opts || {};
    var headers = Object.assign({ Accept: 'application/json' }, o.headers || {});
    if (o.body && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    return fetch(url, {
      method: o.method || 'GET',
      headers: headers,
      body: o.body,
      credentials: 'same-origin',
    }).then(function (res) {
      if (res.status === 204) return null;
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.error) || 'HTTP ' + res.status);
          err.status = res.status;
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  /** Какие кнопки показывать (зависит от env на сервере). */
  function fetchAuthProviders() {
    return jsonFetch('/api/auth/providers').catch(function () {
      return { google: false, telegram: false, telegramBotUsername: null };
    });
  }

  /** Текущий пользователь или null. */
  function fetchMe() {
    return jsonFetch('/api/me').then(function (data) {
      return (data && data.user) || null;
    }).catch(function () {
      return null;
    });
  }

  /** Старт Google OAuth: уходим с текущей страницы. */
  function startGoogleLogin(nextPath) {
    var next = nextPath || (location.pathname + location.search) || '/';
    // Только относительный путь — сервер всё равно валидирует.
    if (next.charAt(0) !== '/') next = '/';
    window.location.href = '/api/auth/google?next=' + encodeURIComponent(next);
  }

  /** Telegram Widget отдал payload → создаём сессию. */
  function loginWithTelegram(payload) {
    return jsonFetch('/api/auth/telegram', {
      method: 'POST',
      body: JSON.stringify(payload),
    }).then(function (data) {
      return (data && data.user) || null;
    });
  }

  function logout() {
    return jsonFetch('/api/auth/logout', { method: 'POST' });
  }

  function fetchWatchlist() {
    return jsonFetch('/api/me/watchlist').then(function (data) {
      return (data && data.ids) || [];
    });
  }

  function putWatchlist(ids) {
    return jsonFetch('/api/me/watchlist', {
      method: 'PUT',
      body: JSON.stringify({ ids: ids || [] }),
    }).then(function (data) {
      return (data && data.ids) || [];
    });
  }

  /** После логина: local ∪ server → сохранить и вернуть. */
  function mergeWatchlist(localIds) {
    return jsonFetch('/api/me/watchlist/merge', {
      method: 'POST',
      body: JSON.stringify({ ids: localIds || [] }),
    }).then(function (data) {
      return (data && data.ids) || [];
    });
  }

  /**
   * Убирает auth=* из query, чтобы редирект Google не открывал модалку снова
   * при каждом refresh.
   */
  function clearAuthQueryParams() {
    try {
      var u = new URL(window.location.href);
      if (!u.searchParams.has('auth') && !u.searchParams.has('provider')) return;
      u.searchParams.delete('auth');
      u.searchParams.delete('provider');
      u.searchParams.delete('reason');
      var qs = u.searchParams.toString();
      window.history.replaceState({}, '', u.pathname + (qs ? '?' + qs : '') + u.hash);
    } catch (e) {}
  }

  function readAuthQuery() {
    try {
      var p = new URLSearchParams(location.search || '');
      return {
        auth: p.get('auth'),
        provider: p.get('provider'),
        reason: p.get('reason'),
      };
    } catch (e) {
      return { auth: null, provider: null, reason: null };
    }
  }

  /**
   * Вставляет Telegram Login Widget в контейнер.
   * onAuth(user) вызывается виджетом через window.__ivanOnTelegramAuth.
   */
  function mountTelegramWidget(container, botUsername, onAuth) {
    if (!container || !botUsername) return;
    container.innerHTML = '';
    global.__ivanOnTelegramAuth = function (user) {
      if (typeof onAuth === 'function') onAuth(user);
    };
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://telegram.org/js/telegram-widget.js?22';
    s.setAttribute('data-telegram-login', botUsername);
    s.setAttribute('data-size', 'large');
    s.setAttribute('data-radius', '20');
    s.setAttribute('data-onauth', '__ivanOnTelegramAuth(user)');
    s.setAttribute('data-request-access', 'write');
    container.appendChild(s);
  }

  global.IVAN = global.IVAN || {};
  Object.assign(global.IVAN, {
    fetchAuthProviders: fetchAuthProviders,
    fetchMe: fetchMe,
    startGoogleLogin: startGoogleLogin,
    loginWithTelegram: loginWithTelegram,
    logout: logout,
    fetchWatchlist: fetchWatchlist,
    putWatchlist: putWatchlist,
    mergeWatchlist: mergeWatchlist,
    clearAuthQueryParams: clearAuthQueryParams,
    readAuthQuery: readAuthQuery,
    mountTelegramWidget: mountTelegramWidget,
  });
})(typeof window !== 'undefined' ? window : globalThis);
