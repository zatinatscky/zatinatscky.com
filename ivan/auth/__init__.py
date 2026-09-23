"""
Авторизация IVAN Terminal: Google OAuth и Telegram Login Widget.

Пользователь входит через провайдера → создаётся/находится запись в users →
в браузер ставится подписанная cookie-сессия. Watchlist после входа живёт в БД
и подтягивается через /api/me/watchlist; до входа — как раньше в localStorage.
"""
