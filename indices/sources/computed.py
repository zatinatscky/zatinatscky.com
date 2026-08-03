"""
Индексы, которых нет ни в одном бесплатном API — считаем сами.

- ssr       — Stablecoin Supply Ratio;
- altseason — Altcoin Season Index.

У обоих платные первоисточники (CryptoQuant и Blockchaincenter), но входные
данные доступны бесплатно и с дневной частотой, поэтому формулы воспроизведены
локально. Методика описана в docstring каждой функции.

BTC Dominance сюда не вошёл: бесплатной истории общей капитализации рынка нет
(у CoinGecko и CoinPaprika это платная опция), а собирать знаменатель из
десятков запросов market_chart нельзя — бесплатный тариф CoinGecko отвечает 429
уже на втором десятке, то есть ежедневная выгрузка была бы ненадёжной.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import binance, blockchain_info, coingecko, defillama

_log = logging.getLogger(__name__)

Point = tuple[str, float]

# Сколько монет из топа участвует в Altcoin Season Index (методика Blockchaincenter).
ALTSEASON_BASKET = 50
# Окно сравнения доходности с BTC.
ALTSEASON_LOOKBACK_DAYS = 90
# Берём топ с запасом: часть монет не торгуется к USDT на Binance.
ALTSEASON_CANDIDATE_POOL = 100

# Стейблкоины и обёрнутые/ставочные производные BTC и ETH: они либо не двигаются,
# либо дублируют базовый актив, поэтому в корзину топ-50 не входят.
ALTSEASON_EXCLUDED_SYMBOLS = frozenset(
    {
        # Стейблкоины
        "usdt", "usdc", "dai", "fdusd", "usde", "tusd", "usds", "pyusd", "usdd",
        "busd", "frax", "lusd", "gusd", "usd1", "rlusd", "eurc", "usdf", "usdx",
        # Обёрнутый и «ставочный» BTC
        "wbtc", "cbbtc", "lbtc", "tbtc", "hbtc", "bnbtc", "solvbtc", "wbeth",
        # Обёрнутый и «ставочный» ETH
        "weth", "steth", "wsteth", "reth", "weeth", "ezeth", "cbeth", "meth",
        # Прочие обёртки
        "wbnb", "wsol", "wtrx", "wpol",
    }
)


def stablecoin_supply_ratio(days: int = 365) -> list[Point]:
    """
    Stablecoin Supply Ratio = капитализация BTC / предложение стейблкоинов.

    Низкий SSR означает, что относительно размера BTC на рынке много «сухого
    пороха» — стейблкоинов, готовых зайти в риск.

    Числитель собирается из двух надёжных бесплатных источников: цена BTC — из
    дневных свечей Binance, число монет в обращении — из blockchain.info.
    Знаменатель — совокупное предложение USD-стейблкоинов из DefiLlama.

    Готовая капитализация с bitcoin-data.com не используется: с того же хоста за
    прогон уже забираются NUPL и MVRV, и третий тяжёлый запрос упирается в лимит.
    """
    supply = blockchain_info.circulating_supply()
    stable = defillama.stablecoin_supply()

    # Свечи с запасом: эмиссия и стейблкоины публикуются по календарным дням.
    start = datetime.now(tz=timezone.utc) - timedelta(days=days + 30)
    prices = binance.fetch_daily_closes("BTCUSDT", int(start.timestamp() * 1000))
    if not prices:
        raise RuntimeError("ssr: нет свечей BTCUSDT")

    points: list[Point] = []
    for day in sorted(prices):
        coins = supply.get(day)
        pool = stable.get(day)
        if not coins or not pool:
            continue
        btc_market_cap = prices[day] * coins
        points.append((day, btc_market_cap / pool))

    if not points:
        raise RuntimeError("ssr: нет дней, где есть и цена BTC, и эмиссия, и стейблкоины")

    _log.info("ssr: %s точек, последняя %s", len(points), points[-1])
    return points


def altseason_index(days: int = 365) -> list[Point]:
    """
    Altcoin Season Index — доля монет из топ-50, обогнавших BTC за 90 дней.

    Методика Blockchaincenter: если 75%+ корзины опередили Bitcoin — «сезон
    альткоинов», меньше 25% — «сезон биткоина», между ними переходная зона.

    Состав корзины берётся одним запросом к CoinGecko (топ по капитализации за
    вычетом стейблкоинов и обёрнутых токенов), а цены — дневными свечами Binance.
    Один запрос к CoinGecko в сутки укладывается в бесплатный лимит с запасом.

    Приближение: состав корзины фиксирован по сегодняшнему топу, тогда как
    исторически он менялся. Это обычный компромисс при обратном расчёте —
    иначе нужна платная история капитализаций.
    """
    coins = coingecko.top_coins(per_page=ALTSEASON_CANDIDATE_POOL)
    tradable = binance.tradable_usdt_symbols()

    # Собираем корзину: пропускаем BTC (он база сравнения), стейблкоины,
    # обёртки и всё, что не торгуется к USDT на Binance.
    basket: list[str] = []
    for coin in coins:
        symbol = str(coin.get("symbol") or "").lower()
        if symbol == "btc" or symbol in ALTSEASON_EXCLUDED_SYMBOLS:
            continue
        pair = f"{symbol.upper()}USDT"
        if pair not in tradable:
            continue
        basket.append(pair)
        if len(basket) >= ALTSEASON_BASKET:
            break

    if len(basket) < 20:
        raise RuntimeError(f"altseason: корзина слишком мала ({len(basket)} пар)")

    # Свечи нужны с запасом на окно сравнения плюс само окно вывода.
    start = datetime.now(tz=timezone.utc) - timedelta(days=days + ALTSEASON_LOOKBACK_DAYS + 10)
    start_ms = int(start.timestamp() * 1000)

    btc_closes = binance.fetch_daily_closes("BTCUSDT", start_ms)
    if not btc_closes:
        raise RuntimeError("altseason: нет свечей BTCUSDT")

    alt_closes: dict[str, dict[str, float]] = {}
    for pair in basket:
        try:
            closes = binance.fetch_daily_closes(pair, start_ms)
            if closes:
                alt_closes[pair] = closes
        except Exception as exc:
            _log.warning("altseason: пропускаем %s (%s)", pair, exc)

    _log.info("altseason: корзина из %s пар со свечами", len(alt_closes))
    if len(alt_closes) < 20:
        raise RuntimeError(f"altseason: свечи получены лишь для {len(alt_closes)} пар")

    def performance(closes: dict[str, float], day: str, ref_day: str) -> float | None:
        """Доходность за окно; None, если на одном из концов нет цены."""
        now, then = closes.get(day), closes.get(ref_day)
        if now is None or then is None or then == 0:
            return None
        return now / then - 1.0

    points: list[Point] = []
    for day in sorted(btc_closes):
        ref_day = (
            datetime.fromisoformat(day).date() - timedelta(days=ALTSEASON_LOOKBACK_DAYS)
        ).isoformat()

        btc_perf = performance(btc_closes, day, ref_day)
        if btc_perf is None:
            continue

        outperformers = 0
        counted = 0
        for closes in alt_closes.values():
            alt_perf = performance(closes, day, ref_day)
            if alt_perf is None:
                continue
            counted += 1
            if alt_perf > btc_perf:
                outperformers += 1

        # Требуем половину корзины, иначе значение на этот день недостоверно.
        if counted < len(alt_closes) // 2:
            continue
        points.append((day, outperformers / counted * 100.0))

    if not points:
        raise RuntimeError("altseason: пустой ряд после расчёта")

    _log.info("altseason: %s точек, последняя %s", len(points), points[-1])
    return points
