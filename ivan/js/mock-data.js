/**
 * Детерминированные мок-данные IVAN Terminal (mulberry32 + seeds из прототипа).
 * window.IVAN.genData(), INDEX_IDS, getIndexById().
 */
(function (global) {
  'use strict';

    var META = [
        {id:'fng',name:'Crypto Fear & Greed',cat:'Sentiment',source:'Alternative.me',url:'https://alternative.me/crypto/fear-and-greed-index/',unit:'',dec:0,min:6,max:92,center:46,vol:5.2,pct:false,gauge:true,seed:101,
          measures:'A single 0–100 score that blends volatility, momentum, volume, social media, dominance and surveys into one read on market emotion.',
          method:'Daily weighted composite of six factors, normalised to 0–100. 0 = extreme fear, 100 = extreme greed.'},
        {id:'altseason',name:'Altcoin Season Index',cat:'Market structure',source:'Blockchaincenter',url:'#',unit:'',dec:0,min:5,max:86,center:33,vol:4.6,pct:false,gauge:true,seed:202,
          measures:'Share of the top-50 coins that have outperformed Bitcoin over the last 90 days.',
          method:'If 75%+ of the top-50 beat BTC it is Altcoin Season; under 25% is Bitcoin Season; in between is transition.'},
        {id:'btcdom',name:'BTC Dominance',cat:'Market structure',source:'CoinGecko',url:'#',unit:'%',dec:1,min:48,max:62,center:56,vol:0.45,pct:true,gauge:false,seed:303,
          measures:"Bitcoin's share of total cryptocurrency market capitalisation.",
          method:'BTC market cap divided by total crypto market cap, expressed as a percentage.'},
        {id:'bvol',name:'Bitcoin Volatility (DVOL)',cat:'Volatility',source:'Deribit',url:'#',unit:'',dec:1,min:33,max:103,center:54,vol:2.9,pct:true,gauge:false,seed:404,
          measures:"Deribit's 30-day forward-looking implied volatility for Bitcoin options — crypto's answer to the VIX.",
          method:'Annualised implied volatility derived from the Deribit BTC options order book.'},
        {id:'nupl',name:'Net Unrealized P/L',cat:'On-chain',source:'Open data',url:'#',unit:'',dec:2,min:-0.12,max:0.71,center:0.42,vol:0.018,pct:false,gauge:false,seed:505,
          measures:'Whether the market in aggregate is sitting in unrealised profit or loss.',
          method:'(Market cap − realised cap) / market cap. Above 0.75 = euphoria, below 0 = capitulation.'},
        {id:'ssr',name:'Stablecoin Supply Ratio',cat:'On-chain',source:'CryptoQuant',url:'#',unit:'',dec:2,min:4.6,max:12.8,center:8.3,vol:0.2,pct:true,gauge:false,seed:606,
          measures:'Buying power of stablecoins relative to Bitcoin — how much dry powder waits on the sidelines.',
          method:'BTC market cap divided by total stablecoin supply. A low SSR signals more potential demand.'},
        {id:'funding',name:'Perp Funding Rate',cat:'Derivatives',source:'Coinglass',url:'#',unit:'%',dec:3,min:-0.024,max:0.058,center:0.012,vol:0.0035,pct:false,gauge:false,seed:707,
          measures:'Average funding paid between long and short perpetual-futures traders across major venues.',
          method:'Open-interest-weighted funding rate. Positive means longs pay shorts — a crowded-long signal.'},
        {id:'mvrv',name:'MVRV Z-Score',cat:'On-chain',source:'Open data',url:'#',unit:'',dec:2,min:-0.4,max:4.4,center:2.0,vol:0.09,pct:false,gauge:false,seed:808,
          measures:'How far price sits above or below an on-chain estimate of fair value.',
          method:'(Market cap − realised cap) / std-dev of market cap. High readings are historically overvalued.'},
        {id:'vix',name:'CBOE VIX',domain:'Equities',sub:'Volatility',country:'USA',source:'CBOE',url:'#',unit:'',dec:1,min:10,max:62,center:17.5,vol:1.1,pct:true,gauge:false,seed:909,
          measures:'Expected 30-day volatility of the S&P 500 implied by option prices — the fear gauge of US equities.',
          method:'Weighted strip of out-of-the-money SPX options across two expirations, annualised.'},
        {id:'spx',name:'S&P 500',domain:'Equities',sub:'Benchmark',country:'USA',source:'S&P DJI',url:'#',unit:'',dec:0,min:4900,max:6400,center:5900,vol:42,pct:true,gauge:false,seed:1001,
          measures:'Capitalisation-weighted benchmark of 500 large US companies — the reference index for global equities.',
          method:'Float-adjusted market-cap weighting, rebalanced quarterly by the index committee.'},
        {id:'stoxx',name:'EURO STOXX 50',domain:'Equities',sub:'Benchmark',country:'Eurozone',source:'STOXX',url:'#',unit:'',dec:0,min:4300,max:5600,center:5050,vol:36,pct:true,gauge:false,seed:1102,
          measures:'Blue-chip benchmark of the 50 largest companies across the Eurozone.',
          method:'Free-float market-cap weighting with a 10% cap per constituent, reviewed annually.'},
        {id:'nikkei',name:'Nikkei 225',domain:'Equities',sub:'Benchmark',country:'Japan',source:'JPX / Nikkei',url:'#',unit:'',dec:0,min:33000,max:45000,center:40200,vol:340,pct:true,gauge:false,seed:1203,
          measures:'Price-weighted index of 225 leading companies on the Tokyo Stock Exchange Prime market.',
          method:'Price-weighted average adjusted by presumed par values, reviewed twice a year.'},
        {id:'cnnfng',name:'Stocks Fear & Greed',domain:'Equities',sub:'Sentiment',country:'USA',source:'CNN Business',url:'#',unit:'',dec:0,min:8,max:94,center:55,vol:4.8,pct:false,gauge:true,seed:1304,
          measures:'A 0–100 composite of seven indicators reading emotion in the US stock market.',
          method:'Equal-weight blend of momentum, breadth, options skew, junk-bond demand and volatility, normalised to 0–100.'},
        {id:'gold',name:'Gold Spot',domain:'Commodities',sub:'Metals',source:'LBMA',url:'#',pre:'$',unit:'',dec:0,min:1950,max:2900,center:2480,vol:20,pct:true,gauge:false,seed:1405,
          measures:'Spot price of one troy ounce of gold — the classic store of value and inflation hedge.',
          method:'Composite of spot quotes from major bullion dealing banks; twice-daily auction reference.'},
        {id:'brent',name:'Brent Crude',domain:'Commodities',sub:'Energy',source:'ICE',url:'#',pre:'$',unit:'',dec:1,min:62,max:98,center:78,vol:1.4,pct:true,gauge:false,seed:1506,
          measures:'Price of North Sea Brent crude oil, the global benchmark for two thirds of traded oil.',
          method:'Front-month ICE Brent futures settlement, rolled on expiry.'},
        {id:'bcom',name:'Commodity Index (BCOM)',domain:'Commodities',sub:'Benchmark',source:'Bloomberg',url:'#',unit:'',dec:1,min:92,max:118,center:103,vol:0.8,pct:true,gauge:false,seed:1607,
          measures:'Broad basket of 24 commodity futures spanning energy, metals, grains and softs.',
          method:'Production- and liquidity-weighted futures basket, capped per sector and rebalanced annually.'},
        {id:'us10y',name:'US 10Y Treasury Yield',domain:'Macro',sub:'Rates',country:'USA',source:'FRED',url:'#',unit:'%',dec:2,min:3.2,max:5.1,center:4.2,vol:0.05,pct:false,gauge:false,seed:1708,
          measures:'Benchmark yield on 10-year US government debt — the anchor for global discount rates.',
          method:'Constant-maturity yield interpolated from the Treasury curve, published daily.'},
        {id:'uscpi',name:'US CPI YoY',domain:'Macro',sub:'Inflation',country:'USA',source:'BLS',url:'#',unit:'%',dec:1,min:2.2,max:4.1,center:2.9,vol:0.07,pct:false,gauge:false,seed:1809,
          measures:'Year-over-year change in US consumer prices — the headline inflation read.',
          method:'Laspeyres-type index of a fixed urban consumption basket, seasonally adjusted.'},
        {id:'cnpmi',name:'China Manufacturing PMI',domain:'Macro',sub:'Business cycle',country:'China',source:'NBS China',url:'#',unit:'',dec:1,min:47.5,max:52.8,center:50.1,vol:0.32,pct:false,gauge:false,seed:1910,
          measures:'Survey of Chinese purchasing managers — above 50 signals expansion, below 50 contraction.',
          method:'Diffusion index over five weighted sub-indices: new orders, output, employment, delivery times, inventories.'},
        {id:'ifo',name:'Ifo Business Climate',domain:'Macro',sub:'Sentiment',country:'Germany',source:'Ifo Institute',url:'#',unit:'',dec:1,min:82,max:95,center:88,vol:0.6,pct:false,gauge:false,seed:2011,
          measures:'Monthly survey of 9,000 German firms on current conditions and six-month expectations.',
          method:'Geometric mean of situation and expectations balances, indexed to 2015 = 100.'},
        {id:'gscpi',name:'Supply Chain Pressure',domain:'Macro',sub:'Supply chains',source:'NY Fed',url:'#',unit:'',dec:2,min:-1.2,max:1.8,center:0.3,vol:0.11,pct:false,gauge:false,seed:2112,
          measures:'Global supply-chain stress from shipping rates, air freight and PMI delivery components.',
          method:'Standard deviations from the historical average of 27 transport-cost and PMI variables.'},
        {id:'dxy',name:'US Dollar Index (DXY)',domain:'FX',sub:'Benchmark',country:'USA',source:'ICE',url:'#',unit:'',dec:1,min:98,max:112,center:104,vol:0.45,pct:true,gauge:false,seed:2213,
          measures:'Value of the US dollar against a basket of six major currencies, euro-heavy.',
          method:'Geometric weighted average of USD exchange rates; EUR 57.6%, JPY 13.6%, GBP 11.9%.'}
      ];

  /** PRNG из прототипа — один и тот же seed даёт один и тот же ряд */
  function mulberry32(a) {
    return function () {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /** Генерация 365 дней дат, BTC, объёма и рядов всех 22 индексов */
  function genData() {
    const N = 365;
    const today = new Date('2026-06-30T00:00:00Z');
    const dates = [];
    for (let i = 0; i < N; i++) {
      const d = new Date(today);
      d.setUTCDate(today.getUTCDate() - (N - 1 - i));
      dates.push(d);
    }
    const r = mulberry32(424242);
    let p = 39000;
    const btc = [];
    const vol = [];
    for (let i = 0; i < N; i++) {
      p = Math.max(16000, p * (1 + (r() - 0.483) * 0.034));
      btc.push(p);
      vol.push(Math.round((9 + r() * 34) * 1e9));
    }
    const indexes = META.map(function (m) {
      const rr = mulberry32(m.seed);
      let v = m.center;
      const s = [];
      for (let i = 0; i < N; i++) {
        v += (m.center - v) * 0.045 + (rr() - 0.5) * m.vol * 2;
        v = Math.max(m.min, Math.min(m.max, v));
        s.push(v);
      }
      return Object.assign({}, m, { series: s });
    });
    return { dates: dates, btc: btc, vol: vol, indexes: indexes };
  }

  var INDEX_IDS = META.map(function (m) {
    return m.id;
  });

  function getIndexById(id) {
    var data = genData();
    return data.indexes.find(function (x) {
      return x.id === id;
    });
  }

  global.IVAN = global.IVAN || {};
  Object.assign(global.IVAN, {
    META: META,
    mulberry32: mulberry32,
    genData: genData,
    INDEX_IDS: INDEX_IDS,
    getIndexById: getIndexById,
  });
})(typeof window !== 'undefined' ? window : globalThis);

