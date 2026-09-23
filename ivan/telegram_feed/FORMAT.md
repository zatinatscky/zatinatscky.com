# Формат поста IVAN → Telegram (тест)

## Картинка
- Окно **14 календарных дней**
- Стиль light-темы терминала (не Plotly): фон `#F7F6F4` / `#EBEBEB`, линия `#DDBA9B`, текст `#013547`
- На карточке: имя, значение, зона, дельты 1d/7d/30d, линия + заливка, `IVAN · 14-day · as of …`
- **Оси X/Y** с засечками и подписями масштаба (Y слева — «красивые» тики; X снизу — даты)
- **Маркер на каждой точке**; **подпись значения** — на последний день и каждые 2 дня ранее (для 14 дней: 7 подписей)
- Рендер: `telegram_feed/chart.py` (`python -m telegram_feed --from-api`)

## Подпись (≤250 символов)
```
🟠 Altcoin Season Index · 42 · Transition
📉 −2.0 (1d) · 📈 +5.0 (7d) · ➡️ +0.0 (30d)
→ https://ivan.zatinatscky.com/i/altseason
——
IVAN · as of 2026-08-03 UTC · NFA
ivan.zatinatscky.com
```

Без блоков «What it means» / «Today’s take».  
В футере только бренд + NFA + ivan.zatinatscky.com (без ссылки на источник данных).

## Охват
- Все **14** индексов терминала, включая Crypto Fear & Greed (`fng`).

## Генерация (без отправки)
```bash
# С продакшен-API (удобно локально)
python -m telegram_feed --from-api --out telegram_feed/out

# Один индекс
python -m telegram_feed --from-api vix

# С Postgres (на VPS / docker)
python -m telegram_feed --out telegram_feed/out
```

Смотреть черновик: `telegram_feed/out/FEED.md`.

## Автопостинг: 14 индексов → 14 каналов
После `indices.sync` systemd-таймер (`deploy/fng-sync.sh`) вызывает:

```bash
python -m telegram_feed.publish
```

Логика:
1. Берёт индексы со **свежим** наблюдением (дата точки ≤ 3 дней от as_of).
2. Для каждого смотрит свой канал (`TELEGRAM_CHANNEL_VIX`, …); без канала — пропуск.
3. Пропускает уже опубликованные (`telegram_post_log` в Postgres).
4. Шлёт PNG + caption в канал индекса, пауза ~2.5 с.
5. Опционально summary в `TELEGRAM_SUMMARY_CHANNEL_ID` / `TELEGRAM_CHANNEL_ID`.

Env (пример):

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL_FNG=@ivan_fng
TELEGRAM_CHANNEL_VIX=@ivan_vix
# … остальные 12 …
# или одной строкой:
# TELEGRAM_CHANNELS={"fng":"@ivan_fng","vix":"@ivan_vix",...}
TELEGRAM_SUMMARY_CHANNEL_ID=@ivan_daily   # опционально
```

```bash
docker compose exec -T web python -m telegram_feed.publish --list-channels
docker compose exec -T web python -m telegram_feed.publish --dry-run
docker compose exec -T web python -m telegram_feed.publish
docker compose exec -T web python -m telegram_feed.publish --force vix
```
