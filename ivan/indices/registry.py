"""
Метаданные индексов IVAN Terminal — единственный источник правды.

Раньше список жил в ivan/js/mock-data.js (константа META) и использовался только
для генерации фейковых рядов. Теперь метаданные отдаёт бэкенд вместе с реальными
значениями (см. app.py, эндпоинт /api/indexes).

Состав отбирался по одному правилу: индекс попадает в терминал, только если его
можно забирать напрямую и обновлять раз в сутки. Из-за этого не вошли:

- месячные показатели (US CPI YoY, China Manufacturing PMI, ifo / OECD BCI,
  NY Fed GSCPI) — обновление раз в месяц, а у части ещё и лаг публикации
  в несколько месяцев;
- EURO STOXX 50, спот золота и Bloomberg Commodity Index — единственным
  бесплатным источником был неофициальный эндпоинт Yahoo Finance, который
  отвечает 429 при регулярных обращениях;
- BTC Dominance — бесплатной истории общей капитализации рынка нет (у CoinGecko
  и CoinPaprika это платная опция), а собирать знаменатель десятками запросов
  market_chart нельзя: бесплатный тариф CoinGecko отдаёт 429 уже на втором
  десятке.

Текстовые поля описания (measures / method / behaviour / reading) выводятся на
странице индекса в блоке «About this index»: что показывает, как считается, что
это говорит о рынке и как читать изменения.

Поля форматирования (unit / pre / dec / pct / gauge) читает фронтенд:
- pre + значение + unit → подпись (valStr в ivan/js/lib.js), например '$91.8' или '4.68%';
- dec                   → знаков после запятой;
- pct=True              → изменение показывать в процентах, а не в пунктах;
- gauge=True            → рисовать полукруглую шкалу 0–100.

Поля domain/sub/country формируют теги и фильтры сайдбара: tagsOf в
ivan/js/lib.js собирает [domain, sub, country].
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Рынки, чей оборот сопоставляется индексам. Какой индекс что получает и почему —
# см. docstring модуля indices/volumes.py.
from .volumes import BTC_PERP, BTC_SPOT, label as volume_label


@dataclass(frozen=True)
class IndexSpec:
    """Описание одного индекса: как показывать и откуда брать."""

    id: str
    name: str
    domain: str
    sub: str
    source: str
    url: str
    # Что показывает индекс.
    measures: str
    # Как считается.
    method: str
    # Что индекс говорит о поведении рынка.
    behaviour: str
    # Какие выводы делают из его изменений.
    reading: str
    # Откуда тянем: ключ фетчера в indices.sources.FETCHERS + его аргументы.
    fetcher: str
    params: dict = field(default_factory=dict)
    # Рынок, чей дневной оборот показывать столбиками под графиком (см. volumes.py).
    # None — объёма у индекса нет, и столбики не рисуются вовсе.
    volume_market: str | None = None
    country: str | None = None
    unit: str = ""
    pre: str = ""
    dec: int = 2
    pct: bool = False
    gauge: bool = False


# Порядок в списке = порядок карточек в терминале.
SPECS: tuple[IndexSpec, ...] = (
    # --------------------------------------------------------------- Crypto
    IndexSpec(
        id="fng",
        name="Crypto Fear & Greed",
        domain="Crypto",
        sub="Sentiment",
        source="Alternative.me",
        url="https://alternative.me/crypto/fear-and-greed-index/",
        dec=0,
        gauge=True,
        measures=(
            "A single 0–100 score summarising the prevailing emotional state of the "
            "cryptocurrency market, where 0 is extreme fear and 100 is extreme greed."
        ),
        method=(
            "A daily weighted composite of six inputs: price volatility, market momentum "
            "and volume, social-media activity, Bitcoin dominance, search trends and "
            "surveys. Each input is normalised and blended into one 0–100 reading."
        ),
        behaviour=(
            "Sentiment indices describe crowd positioning rather than fundamentals. Fear "
            "readings mean participants have already de-risked and hold cash; greed "
            "readings mean exposure is high and leverage has accumulated. The index "
            "therefore tracks how much room the market still has to move in each direction."
        ),
        reading=(
            "Extremes are traditionally read contrarian: sustained values below 25 have "
            "historically clustered near local price bottoms, while values above 75 "
            "indicate an overheated market vulnerable to a correction. Mid-range values "
            "carry little signal on their own — there the direction of travel matters more "
            "than the level."
        ),
        fetcher="alternative_me_fng",
        volume_market=BTC_SPOT,
    ),
    IndexSpec(
        id="altseason",
        name="Altcoin Season Index",
        domain="Crypto",
        sub="Market structure",
        source="Binance (computed)",
        url="https://www.binance.com/en/markets",
        dec=0,
        gauge=True,
        measures=(
            "The breadth of altcoin outperformance: what share of the 50 largest coins has "
            "delivered a higher 90-day return than Bitcoin."
        ),
        method=(
            "The basket is the top 50 coins by market capitalisation, excluding stablecoins "
            "and wrapped or staked derivatives of Bitcoin and Ether. For every day, each "
            "coin's 90-day return is compared with Bitcoin's over the same window, and the "
            "share of outperformers is expressed on a 0–100 scale. Prices come from daily "
            "Binance candles."
        ),
        behaviour=(
            "The index measures how capital rotates inside crypto. Money tends to enter the "
            "market through Bitcoin first and only later spreads down the capitalisation "
            "curve, so broad altcoin outperformance is a sign that risk appetite has "
            "extended beyond the largest asset."
        ),
        reading=(
            "Above 75 the market is in an altcoin season — a late-cycle condition where "
            "speculative appetite is broad and drawdowns tend to be sharp. Below 25 capital "
            "is concentrating in Bitcoin, which usually accompanies risk reduction or a "
            "defensive market. A steady rise from low levels indicates liquidity spreading "
            "across the market; a sharp fall indicates a flight back to quality."
        ),
        fetcher="altseason",
    ),
    IndexSpec(
        id="bvol",
        name="Bitcoin Volatility (DVOL)",
        domain="Crypto",
        sub="Volatility",
        source="Deribit",
        url="https://www.deribit.com/statistics/BTC/volatility-index",
        dec=1,
        pct=True,
        measures=(
            "The volatility the options market expects in Bitcoin over the coming 30 days, "
            "annualised — the crypto equivalent of the VIX."
        ),
        method=(
            "Implied volatility derived from the Deribit Bitcoin options order book across "
            "strikes and expiries, annualised into a single forward-looking number."
        ),
        behaviour=(
            "DVOL is the market price of protection. It rises when participants pay up to "
            "hedge, which happens when positioning is stretched and the range of plausible "
            "outcomes widens. Unlike sentiment surveys it reflects money actually committed "
            "to hedging, so it responds to stress faster than price-based indicators."
        ),
        reading=(
            "Sharp spikes accompany forced liquidations and usually coincide with capitulation "
            "rather than precede it, so they tend to mean-revert. Prolonged low readings "
            "indicate complacency and compressed positioning, a state that historically "
            "precedes an expansion in realised volatility in either direction."
        ),
        fetcher="deribit_dvol",
        params={"currency": "BTC"},
        volume_market=BTC_SPOT,
    ),
    IndexSpec(
        id="nupl",
        name="Net Unrealized P/L",
        domain="Crypto",
        sub="On-chain",
        source="bitcoin-data.com",
        url="https://bitcoin-data.com/",
        dec=2,
        measures=(
            "Whether Bitcoin holders in aggregate are sitting on an unrealised profit or an "
            "unrealised loss, as a fraction of market capitalisation."
        ),
        method=(
            "Market capitalisation minus realised capitalisation, divided by market "
            "capitalisation. Realised capitalisation values every coin at the price at which "
            "it last moved on-chain, which approximates the market's aggregate cost basis."
        ),
        behaviour=(
            "The measure describes the incentive to sell. When most coins are held at a "
            "profit, holders have a reason to take it, and supply tends to come to market on "
            "strength. When the average holder is underwater, sellers are exhausted and "
            "remaining supply is held by participants unwilling to realise a loss."
        ),
        reading=(
            "Readings above roughly 0.75 mark euphoria and have historically coincided with "
            "distribution near cycle tops. Readings below zero mean the average holder is at "
            "a loss — a capitulation zone that historically overlapped with accumulation "
            "ranges. A steady climb through the middle of the range is consistent with an "
            "intact uptrend."
        ),
        fetcher="bitcoin_data",
        params={"path": "nupl", "value_key": "nupl"},
        volume_market=BTC_SPOT,
    ),
    IndexSpec(
        id="ssr",
        name="Stablecoin Supply Ratio",
        domain="Crypto",
        sub="On-chain",
        source="Binance + DefiLlama",
        url="https://defillama.com/stablecoins",
        dec=2,
        pct=True,
        measures=(
            "The size of Bitcoin relative to the stablecoin float — how much purchasing power "
            "is waiting on the sidelines against the value of the asset it could buy."
        ),
        method=(
            "Bitcoin's market capitalisation divided by the total supply of dollar-pegged "
            "stablecoins. Capitalisation is the daily Binance close multiplied by the number "
            "of coins in circulation reported by blockchain.info; stablecoin supply comes "
            "from DefiLlama."
        ),
        behaviour=(
            "Stablecoins are the market's cash balance: capital that has entered crypto but "
            "has not yet been deployed into risk. The ratio therefore tracks latent demand "
            "rather than sentiment — a falling ratio means the cash pile is growing faster "
            "than Bitcoin's valuation."
        ),
        reading=(
            "A low ratio means ample dry powder relative to Bitcoin's size and is a "
            "supportive backdrop for demand. A high ratio means the available cash is thin "
            "against current valuations, so further gains have to come from new inflows "
            "rather than from capital already sitting in the market."
        ),
        fetcher="stablecoin_supply_ratio",
        volume_market=BTC_SPOT,
    ),
    IndexSpec(
        id="funding",
        name="Perp Funding Rate",
        domain="Crypto",
        sub="Derivatives",
        source="Binance Futures",
        url="https://www.binance.com/en/futures/funding-history",
        unit="%",
        dec=3,
        measures=(
            "The periodic payment exchanged between long and short holders of the Bitcoin "
            "perpetual futures contract — the running cost of leveraged exposure."
        ),
        method=(
            "The daily mean of the BTCUSDT perpetual funding rate, which settles three times "
            "a day, expressed in percent. A positive value means longs pay shorts."
        ),
        behaviour=(
            "Funding reveals which side of the market is crowded and what it is paying to "
            "stay there. Because the rate is set by the imbalance between the perpetual "
            "price and spot, it is a direct read on leveraged positioning rather than on "
            "opinion, and crowded positioning is what makes liquidation cascades possible."
        ),
        reading=(
            "Persistently elevated positive funding indicates crowded longs paying to hold "
            "exposure, which raises the risk of a long squeeze on any downward move. "
            "Negative funding indicates crowded shorts and provides fuel for a short "
            "squeeze on strength. Values near zero describe balanced positioning and carry "
            "little directional information."
        ),
        fetcher="binance_funding",
        params={"symbol": "BTCUSDT"},
        # Ставка рассчитывается по бессрочному контракту, поэтому и оборот берём
        # по нему, а не по споту.
        volume_market=BTC_PERP,
    ),
    IndexSpec(
        id="mvrv",
        name="MVRV Z-Score",
        domain="Crypto",
        sub="On-chain",
        source="bitcoin-data.com",
        url="https://bitcoin-data.com/",
        dec=2,
        measures=(
            "How far Bitcoin's price sits above or below the aggregate on-chain cost basis, "
            "measured in standard deviations."
        ),
        method=(
            "Market capitalisation minus realised capitalisation, divided by the standard "
            "deviation of market capitalisation. The Z-score normalisation makes readings "
            "comparable across cycles despite the growth in absolute market size."
        ),
        behaviour=(
            "The score is a valuation measure anchored to what holders actually paid rather "
            "than to earnings or cash flows. It expands when price runs far ahead of the "
            "market's cost basis and compresses when price falls back towards it, which is "
            "why its extremes have lined up with cycle turning points."
        ),
        reading=(
            "Historically high readings have marked overvalued, late-cycle conditions where "
            "risk-reward deteriorates, while readings at or below zero have marked deep-value "
            "conditions where price trades near or under the aggregate cost basis. Between "
            "the extremes the score is best used to gauge where in a cycle the market sits, "
            "not to time entries."
        ),
        fetcher="bitcoin_data",
        params={"path": "mvrv-zscore", "value_key": "mvrvZscore"},
        volume_market=BTC_SPOT,
    ),
    # ------------------------------------------------------------- Equities
    IndexSpec(
        id="vix",
        name="CBOE VIX",
        domain="Equities",
        sub="Volatility",
        country="USA",
        source="CBOE / FRED",
        url="https://fred.stlouisfed.org/series/VIXCLS",
        dec=1,
        pct=True,
        measures=(
            "The volatility the options market expects in the S&P 500 over the coming 30 "
            "days, annualised — the reference fear gauge for US equities."
        ),
        method=(
            "Calculated from a weighted strip of out-of-the-money S&P 500 option prices "
            "across the two nearest expiries and annualised."
        ),
        behaviour=(
            "The VIX prices the demand for equity protection and is the anchor for global "
            "risk appetite. It moves inversely to equities and rises faster than it falls, "
            "because hedging demand appears abruptly during stress and decays slowly. Crypto "
            "correlates with equities most strongly precisely when the VIX is elevated."
        ),
        reading=(
            "Readings below 15 indicate a calm, complacent market where hedges are cheap. "
            "The 20–30 band indicates genuine stress and widening uncertainty. Readings above "
            "30 signal panic and have historically clustered around capitulation lows rather "
            "than at the start of declines, since spikes tend to mean-revert quickly."
        ),
        fetcher="fred",
        params={"series_id": "VIXCLS"},
    ),
    IndexSpec(
        id="spx",
        name="S&P 500",
        domain="Equities",
        sub="Benchmark",
        country="USA",
        source="S&P DJI / FRED",
        url="https://fred.stlouisfed.org/series/SP500",
        dec=0,
        pct=True,
        measures=(
            "The benchmark index of 500 large US companies and the reference point for global "
            "equity risk."
        ),
        method=(
            "Float-adjusted market-capitalisation weighting of its constituents, with the "
            "membership reviewed quarterly by the index committee."
        ),
        behaviour=(
            "The index aggregates expectations for corporate earnings and for the discount "
            "rate applied to them, which makes it the cleanest single read on global risk "
            "appetite. It sets the tone for other risk assets: crypto's correlation with it "
            "is loose in calm markets and tightens sharply during broad de-risking."
        ),
        reading=(
            "Sustained advances to new highs describe a risk-on environment supportive of "
            "other risk assets. Rapid drawdowns generally spill into crypto with a higher "
            "beta, so weakness here is a warning for the rest of the terminal. Divergence — "
            "equities holding while crypto falls — usually points to a cause specific to "
            "crypto rather than to macro conditions."
        ),
        fetcher="fred",
        params={"series_id": "SP500"},
    ),
    IndexSpec(
        id="nikkei",
        name="Nikkei 225",
        domain="Equities",
        sub="Benchmark",
        country="Japan",
        source="JPX / Nikkei",
        url="https://fred.stlouisfed.org/series/NIKKEI225",
        dec=0,
        pct=True,
        measures="The benchmark index of 225 leading companies listed on the Tokyo Stock Exchange Prime market.",
        method=(
            "A price-weighted average adjusted by presumed par values, with the constituent "
            "list reviewed twice a year."
        ),
        behaviour=(
            "Beyond Japanese equities, the Nikkei is the most liquid daily proxy for the yen "
            "carry trade. Japan has long been the cheapest place to borrow, and that borrowed "
            "money funds risk positions worldwide, so the index reflects the availability of "
            "global funding rather than only domestic earnings."
        ),
        reading=(
            "Steady gains alongside a weakening yen describe an intact carry trade and ample "
            "global funding. Sharp declines accompanied by a strengthening yen are the "
            "signature of a carry unwind, in which leveraged positions are closed across all "
            "markets at once — historically one of the fastest routes to global risk-off, "
            "including in crypto."
        ),
        fetcher="fred",
        params={"series_id": "NIKKEI225"},
    ),
    IndexSpec(
        id="cnnfng",
        name="Stocks Fear & Greed",
        domain="Equities",
        sub="Sentiment",
        country="USA",
        source="CNN Business",
        url="https://edition.cnn.com/markets/fear-and-greed",
        dec=0,
        gauge=True,
        measures=(
            "A 0–100 composite of seven indicators describing the emotional state of the US "
            "stock market."
        ),
        method=(
            "An equal-weight blend of price momentum, market breadth, new highs versus lows, "
            "put/call skew, junk-bond demand, market volatility and safe-haven demand, each "
            "normalised and combined into a 0–100 score."
        ),
        behaviour=(
            "Unlike a survey, this index infers emotion from positioning that has already "
            "been paid for — option skew, credit spreads and breadth. It therefore describes "
            "what equity investors have actually done, and gives a cross-check on the crypto "
            "sentiment gauge: when both sit at an extreme, the driver is macro rather than "
            "crypto-specific."
        ),
        reading=(
            "Values below 25 mark capitulation in equities, historically a favourable "
            "risk-reward zone for buyers. Values above 75 mark complacency, where positioning "
            "is stretched and adverse news has more impact. As with all sentiment measures, "
            "the extremes are contrarian while mid-range values mainly confirm the trend."
        ),
        fetcher="cnn_fng",
    ),
    # ---------------------------------------------------------- Commodities
    IndexSpec(
        id="brent",
        name="Brent Crude",
        domain="Commodities",
        sub="Energy",
        source="EIA / FRED",
        url="https://fred.stlouisfed.org/series/DCOILBRENTEU",
        pre="$",
        dec=1,
        pct=True,
        measures=(
            "The price of a barrel of North Sea Brent crude oil, the pricing benchmark for "
            "roughly two thirds of internationally traded oil."
        ),
        method="Europe Brent spot price free on board, published daily.",
        behaviour=(
            "Oil sits at the intersection of growth, geopolitics and inflation. Demand-driven "
            "moves track the strength of the global economy, while supply-driven moves feed "
            "straight into headline inflation and therefore into interest-rate expectations. "
            "That second channel is what transmits oil into the valuation of risk assets."
        ),
        reading=(
            "A rapid supply-driven rise raises inflation expectations and pushes central "
            "banks towards tighter policy, which is a headwind for long-duration and "
            "speculative assets including crypto. A sustained decline usually signals "
            "weakening demand: disinflationary and supportive for rate-sensitive assets, but "
            "a warning about the growth outlook."
        ),
        fetcher="fred",
        params={"series_id": "DCOILBRENTEU"},
    ),
    # ---------------------------------------------------------------- Macro
    IndexSpec(
        id="us10y",
        name="US 10Y Treasury Yield",
        domain="Macro",
        sub="Rates",
        country="USA",
        source="FRED",
        url="https://fred.stlouisfed.org/series/DGS10",
        unit="%",
        dec=2,
        measures=(
            "The yield on ten-year US government debt — the benchmark long-term risk-free "
            "rate."
        ),
        method=(
            "A constant-maturity yield interpolated from the US Treasury yield curve and "
            "published every business day."
        ),
        behaviour=(
            "This yield is the discount rate against which every other asset is valued. It "
            "combines expectations for growth, inflation and central-bank policy into one "
            "number, and it determines the opportunity cost of holding assets that generate "
            "no yield — which is precisely the category Bitcoin and gold belong to."
        ),
        reading=(
            "A rapid rise compresses the valuation of long-duration and speculative assets, "
            "because future cash flows are discounted harder and risk-free alternatives "
            "become more attractive. A decline driven by falling inflation is supportive, "
            "whereas a sharp decline driven by growth fear signals a flight to quality and "
            "usually coincides with risk-off across equities and crypto."
        ),
        fetcher="fred",
        params={"series_id": "DGS10"},
    ),
    # ------------------------------------------------------------------- FX
    IndexSpec(
        id="dxy",
        name="US Dollar Index (DXY)",
        domain="FX",
        sub="Benchmark",
        country="USA",
        source="ECB reference rates (computed)",
        url="https://www.ecb.europa.eu/stats/eurofxref/",
        dec=1,
        pct=True,
        measures=(
            "The value of the US dollar against a basket of six major currencies, weighted "
            "towards the euro."
        ),
        method=(
            "The published DXY formula applied to daily European Central Bank reference "
            "rates: a geometric weighted average of the dollar against the euro (57.6%), yen "
            "(13.6%), pound (11.9%), Canadian dollar (9.1%), Swedish krona (4.2%) and Swiss "
            "franc (3.6%)."
        ),
        behaviour=(
            "The dollar is the funding currency of the global financial system, so its "
            "exchange rate is a proxy for how tight or loose global liquidity is. A rising "
            "dollar raises the real cost of dollar-denominated debt worldwide and drains "
            "liquidity from risk markets; a falling dollar does the opposite."
        ),
        reading=(
            "Sustained dollar strength is a headwind for crypto, commodities and emerging "
            "markets, since it tightens global financial conditions regardless of what "
            "domestic policy is doing. Sustained weakness is a tailwind for the same assets. "
            "Abrupt spikes typically accompany a scramble for dollar liquidity, in which "
            "correlations across risk assets rise towards one."
        ),
        fetcher="dxy_from_ecb",
    ),
)

# Быстрый доступ по id и проверка уникальности при импорте.
BY_ID: dict[str, IndexSpec] = {}
for _spec in SPECS:
    if _spec.id in BY_ID:
        raise ValueError(f"Дубликат id индекса в registry: {_spec.id}")
    BY_ID[_spec.id] = _spec

INDEX_IDS: tuple[str, ...] = tuple(s.id for s in SPECS)


def meta_dict(spec: IndexSpec) -> dict:
    """Метаданные в том виде, в каком их ждёт фронтенд (ivan/js/lib.js, app.js)."""
    return {
        "id": spec.id,
        "name": spec.name,
        "domain": spec.domain,
        "sub": spec.sub,
        "country": spec.country,
        "source": spec.source,
        "url": spec.url,
        "unit": spec.unit,
        "pre": spec.pre,
        "dec": spec.dec,
        "pct": spec.pct,
        "gauge": spec.gauge,
        "measures": spec.measures,
        "method": spec.method,
        "behaviour": spec.behaviour,
        "reading": spec.reading,
        # Подпись рынка для легенды объёма; None — столбики не рисуем.
        "volumeLabel": volume_label(spec.volume_market),
    }
