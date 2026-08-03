/**
 * IVAN Terminal — React 18 (createElement, без JSX).
 * Страница home/detail задаётся через document.body.dataset, не через SPA-state.
 */
(function (global) {
  'use strict';

  var React = global.React;
  var ReactDOM = global.ReactDOM;
  var IVAN = global.IVAN;
  var Charts = global.IVANCharts;
  var h = React.createElement;

  /** Разбор inline CSS-строк прототипа в объект для React style */
  function ps(css) {
    var o = {};
    if (!css) return o;
    String(css)
      .split(';')
      .forEach(function (part) {
        var i = part.indexOf(':');
        if (i > 0) {
          var k = part.slice(0, i).trim();
          var v = part.slice(i + 1).trim();
          if (k) o[k] = v;
        }
      });
    return o;
  }

  function mergeStyle() {
    var o = {};
    for (var i = 0; i < arguments.length; i++) {
      Object.assign(o, ps(arguments[i]));
    }
    return o;
  }

  /** CSS-переменные темы на корневом контейнере */
  function rootStyleObj(theme, accent) {
    return ps(IVAN.rootStyleCss(theme, accent));
  }

  /** Класс приложения — состояние UI как в прототипе terminal.dc.html */
  class IvanApp extends React.Component {
    constructor(props) {
      super(props);
      // Реальные данные из /api/indexes, загружены в IVAN.boot() до первого рендера.
      this.data = props.data;
      this.state = {
        theme: (props && props.theme) || 'light',
        // Handoff default accent (#DDBA9B) — линии графиков, CTA, chips.
        accent: (props && props.accent) || '#DDBA9B',
        layout:
          typeof IVAN !== 'undefined' && IVAN.readInitialLayout
            ? IVAN.readInitialLayout()
            : (props && props.layout) || 'grid',
        q: '',
        // На home подхватываем ?cat= / sessionStorage (фильтр с detail).
        cat:
          props && props.page === 'home' && typeof IVAN !== 'undefined' && IVAN.readInitialCat
            ? IVAN.readInitialCat()
            : 'all',
        range: '90d',
        hover: null,
        collapsed: false,
        tickIdx: 0,
        tickOff: 0,
        tickAnim: false,
        compare: [],
        sort: 'featured',
        reqOpen: false,
        reqSent: false,
        welcomeOpen: false,
        welcomeDismiss: false,
        welcomeExit: false,
        entering: false,
        watch: [],
        watchOpen: false,
        alerts: {},
        alertOp: 'below',
        alertVal: '',
        selIdx: -1,
        cmpWith: 'none',
        cmpQuery: '',
        cmpOpen: false,
        cmpSel: 0,
        yoursOpen: true,
        browseOpen: true,
      };
      this._cards = {};
      this._ids = [];
      this._cmpRes = [];
      this._search = null;
      this._tip = null;
      this._tickPaused = false;
    }

    /** Текущая страница и id индекса — только из props (MPA) */
    page() {
      return this.props.page || 'home';
    }

    indexId() {
      return this.props.indexId || null;
    }

    componentDidMount() {
      var self = this;
      var onHome = this.page() === 'home';

      // Welcome, watchlist, alerts из localStorage
      if (!IVAN.isWelcomeDismissed()) {
        this.setState({ welcomeOpen: true });
      } else if (onHome) {
        IVAN.restoreHomeScroll();
      }

      var w = IVAN.loadWatchlist();
      if (w.length) this.setState({ watch: w });

      var alerts = IVAN.loadAlerts();
      if (alerts && typeof alerts === 'object') this.setState({ alerts: alerts });

      this.initDetailForm();

      this._onKey = function (e) {
        var t = e.target;
        var tag = t && t.tagName;
        var typing = tag === 'INPUT' || tag === 'TEXTAREA';
        var st = self.state;

        if (e.key === 'Escape') {
          if (typing) {
            t.blur();
            return;
          }
          if (st.cmpOpen) {
            self.setState({ cmpOpen: false });
            return;
          }
          if (st.watchOpen) {
            self.setState({ watchOpen: false });
            return;
          }
          if (st.reqOpen) {
            self.setState({ reqOpen: false });
            return;
          }
          if (self.page() === 'detail') {
            IVAN.goHome();
          }
          return;
        }

        if (typing || e.metaKey || e.ctrlKey || e.altKey) return;

        if (e.key === '/') {
          e.preventDefault();
          // В прототипе / всегда ведёт на home + фокус поиска.
          if (self.page() !== 'home') {
            IVAN.goHome();
            return;
          }
          if (self._search) self._search.focus();
          return;
        }

        var n = (self._ids || []).length;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          if (self.page() !== 'home' || !n) return;
          e.preventDefault();
          var step = e.key === 'ArrowDown' ? 1 : -1;
          var cur = st.selIdx;
          var next =
            cur < 0 ? (step > 0 ? 0 : n - 1) : Math.min(n - 1, Math.max(0, cur + step));
          self.setState({ selIdx: next });
          self.scrollToCard(next);
          return;
        }

        if (e.key === 'Enter') {
          if (self.page() === 'home' && st.selIdx >= 0 && self._ids[st.selIdx]) {
            e.preventDefault();
            self.openIndex(self._ids[st.selIdx]);
          }
          return;
        }

        var k = e.key.toLowerCase();
        if (k === 's') {
          var id =
            self.page() === 'detail'
              ? self.indexId()
              : (self._ids || [])[st.selIdx];
          if (id) {
            e.preventDefault();
            self.toggleWatch(id);
          }
          return;
        }
        if (k === 'w') {
          e.preventDefault();
          self.setState({ watchOpen: !st.watchOpen });
        }
      };

      global.addEventListener('keydown', this._onKey);

      this._tk = setInterval(function () {
        if (self._tickPaused) return;
        self.setState({ tickOff: 1, tickAnim: true });
        self._tk2 = setTimeout(function () {
          self.setState(function (prev) {
            return {
              tickIdx: (prev.tickIdx + 1) % self.data.indexes.length,
              tickOff: 0,
              tickAnim: false,
            };
          });
        }, 600);
      }, 2800);
    }

    componentDidUpdate(prevProps) {
      if (prevProps.indexId !== this.props.indexId || prevProps.page !== this.props.page) {
        this.initDetailForm();
      }
    }

    componentWillUnmount() {
      clearInterval(this._tk);
      clearTimeout(this._tk2);
      if (this._onKey) global.removeEventListener('keydown', this._onKey);
    }

    /** Поля alert на детальной странице при загрузке / смене indexId */
    initDetailForm() {
      if (this.page() !== 'detail' || !this.indexId()) return;
      var m = this.data.indexes.find(function (x) {
        return x.id === this.indexId();
      }, this);
      if (!m) return;
      var a = this.state.alerts[this.indexId()];
      var cur = m.series[m.series.length - 1];
      this.setState({
        range: '90d',
        hover: null,
        cmpWith: 'none',
        cmpQuery: '',
        cmpOpen: false,
        alertOp: a ? a.op : 'below',
        alertVal: a ? String(a.value) : String(Number(cur.toFixed(m.dec))),
      });
    }

    scrollToCard(i) {
      var self = this;
      requestAnimationFrame(function () {
        var el = self._cards && self._cards[i];
        if (!el || !el.getBoundingClientRect) return;
        var r = el.getBoundingClientRect();
        if (r.top < 150 || r.bottom > global.innerHeight - 40) {
          global.scrollTo({ top: global.scrollY + r.top - 190, behavior: 'smooth' });
        }
      });
    }

    openIndex(id) {
      IVAN.navigateToIndex(id);
    }

    /**
     * Фильтр по тегу (как в прототипе setState({cat, page:'home'})).
     * На detail — полный переход на главную с ?cat=.
     */
    applyFilter(cat) {
      var next = cat || 'all';
      if (this.page() === 'home') {
        this.setState({ cat: next, watchOpen: false, selIdx: -1 });
        try {
          if (next !== 'all') sessionStorage.setItem('ivan_cat', next);
          else sessionStorage.removeItem('ivan_cat');
          var path = location.pathname;
          var url = next !== 'all' ? path + '?cat=' + encodeURIComponent(next) : path;
          if (window.history && history.replaceState) history.replaceState(null, '', url);
        } catch (e) {}
      } else {
        IVAN.goHomeWithFilter(next);
      }
    }

    setLayout(layout) {
      this.setState({ layout: layout });
      if (IVAN.saveLayout) IVAN.saveLayout(layout);
    }

    pickCmp(id, label) {
      this.setState({ cmpWith: id, cmpQuery: label, cmpOpen: false, hover: null });
    }

    setAlert(id) {
      var v = parseFloat(String(this.state.alertVal).replace(',', '.'));
      if (!isFinite(v)) return;
      var A = Object.assign({}, this.state.alerts);
      A[id] = { op: this.state.alertOp, value: v };
      this.setState({ alerts: A });
      IVAN.saveAlerts(A);
    }

    removeAlert(id) {
      var A = Object.assign({}, this.state.alerts);
      delete A[id];
      this.setState({ alerts: A });
      IVAN.saveAlerts(A);
    }

    toggleCompare(id) {
      var c = this.state.compare.slice();
      var i = c.indexOf(id);
      if (i >= 0) c.splice(i, 1);
      else if (c.length < 3) c.push(id);
      this.setState({ compare: c });
    }

    toggleWatch(id) {
      var w = this.state.watch.slice();
      var i = w.indexOf(id);
      if (i >= 0) w.splice(i, 1);
      else w.push(id);
      this.setState({ watch: w });
      IVAN.saveWatchlist(w);
    }

    starStyle(active) {
      return (
        'width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid ' +
        (active ? 'var(--accent)' : 'var(--hairline)') +
        ';background:' +
        (active ? 'var(--accent)' : 'transparent') +
        ';color:' +
        (active ? 'var(--on-accent)' : 'var(--text-faint)') +
        ';font-size:12px;line-height:1;cursor:pointer;flex-shrink:0;transition:all .18s;'
      );
    }

    cmpStyle(active) {
      return (
        'width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid ' +
        (active ? 'var(--accent)' : 'var(--hairline)') +
        ';background:' +
        (active ? 'var(--accent)' : 'transparent') +
        ';color:' +
        (active ? 'var(--on-accent)' : 'var(--text-faint)') +
        ';font:600 12px/1 Archivo;cursor:pointer;flex-shrink:0;transition:background .15s,border-color .15s,color .15s;'
      );
    }

    tagStyle(active) {
      return (
        'display:inline-flex;align-items:center;height:26px;padding:0 11px;border-radius:999px;border:1px solid ' +
        (active ? 'var(--accent)' : 'var(--hairline)') +
        ';background:' +
        (active ? 'var(--accent)' : 'transparent') +
        ';color:' +
        (active ? 'var(--on-accent)' : 'var(--text-dim)') +
        ';font:500 11px Archivo;cursor:pointer;transition:background .2s,color .2s,border-color .2s;white-space:nowrap;'
      );
    }

    segStyle(active) {
      return (
        'flex:1;display:inline-flex;align-items:center;justify-content:center;height:30px;padding:0 12px;border-radius:999px;border:none;cursor:pointer;font:600 12px Archivo;background:' +
        (active ? 'var(--accent)' : 'transparent') +
        ';color:' +
        (active ? 'var(--on-accent)' : 'var(--text-dim)') +
        ';transition:background .2s,color .2s;'
      );
    }

    rangeStyle(active) {
      return (
        'display:inline-flex;align-items:center;height:26px;padding:0 12px;border-radius:999px;border:none;cursor:pointer;font:500 11.5px IBM Plex Mono;background:' +
        (active ? 'var(--accent)' : 'transparent') +
        ';color:' +
        (active ? 'var(--on-accent)' : 'var(--text-dim)') +
        ';transition:background .2s,color .2s;'
      );
    }

    buildItem(meta, featured, i) {
      var self = this;
      var st = this.state;
      var s = meta.series;
      var cur = s[s.length - 1];
      var c24 = IVAN.fmtChange(meta, cur, s[s.length - 2]);
      var c7 = IVAN.fmtChange(meta, cur, s[s.length - 8]);
      var c30 = IVAN.fmtChange(meta, cur, s[s.length - 31]);
      var z = IVAN.zoneOf(meta, cur);
      var tg = IVAN.tagsOf(meta);
      var cmpActive = st.compare.indexOf(meta.id) >= 0;
      var watched = st.watch.indexOf(meta.id) >= 0;
      var span =
        (featured ? 'grid-column:span 2;' : '') +
        (i != null && st.selIdx === i ? 'outline:2px solid var(--accent);outline-offset:3px;' : '') +
        (st.entering && i != null
          ? 'animation:ivwCard .72s ' +
            (0.12 + Math.min(i, 11) * 0.055).toFixed(2) +
            's cubic-bezier(.16,1,.3,1) both;'
          : '');

      return {
        id: meta.id,
        name: meta.name,
        tags: tg,
        tagsStr: tg.join(' · '),
        source: meta.source,
        statusLabel: 'LIVE',
        cmpIcon: cmpActive ? '✓' : '+',
        cmpStyle: this.cmpStyle(cmpActive),
        starIcon: watched ? '★' : '☆',
        starStyle: this.starStyle(watched),
        span: span,
        valueStr: IVAN.valStr(meta, cur),
        zoneLabel: z.label,
        zoneColor: z.color,
        chg24: c24.txt,
        chg24Color: c24.up ? 'var(--up)' : 'var(--down)',
        chg7: c7.txt,
        chg7Color: c7.up ? 'var(--up)' : 'var(--down)',
        chg30: c30.txt,
        chg30Color: c30.up ? 'var(--up)' : 'var(--down)',
        spark: Charts.spark(React, s, featured ? 300 : 124, 40),
        sparkSm: Charts.spark(React, s, 86, 26),
        featured: featured,
        cardIndex: i,
      };
    }

    detailData(meta) {
      var s = meta.series;
      var cur = s[s.length - 1];
      var z = IVAN.zoneOf(meta, cur);
      var c24 = IVAN.fmtChange(meta, cur, s[s.length - 2]);
      var c7 = IVAN.fmtChange(meta, cur, s[s.length - 8]);
      var c30 = IVAN.fmtChange(meta, cur, s[s.length - 31]);
      var lo = Math.min.apply(null, s);
      var hiv = Math.max.apply(null, s);
      var avg = s.slice(-90).reduce(function (a, b) {
        return a + b;
      }, 0) / 90;
      var pct = Math.round(
        (s.filter(function (x) {
          return x <= cur;
        }).length /
          s.length) *
          100
      );
      var col = function (x) {
        return x.up ? 'var(--up)' : 'var(--down)';
      };
      var zc = ('' + z.color).indexOf('var(--accent-strong)') === 0 ? 'var(--tone)' : z.color;
      var tg = IVAN.tagsOf(meta);
      var self = this;
      var d = {
        name: meta.name,
        cat: tg.join(' · '),
        source: meta.source,
        valueStr: IVAN.valStr(meta, cur),
        zoneLabel: z.label,
        zoneColor: meta.gauge ? z.color : zc,
        hasGauge: !!meta.gauge,
        noGauge: !meta.gauge,
        c24: c24.txt,
        c24c: col(c24),
        c7: c7.txt,
        c7c: col(c7),
        c30: c30.txt,
        c30c: col(c30),
        reading: meta.measures,
      };
      var stats = [
        { label: 'Current', value: IVAN.valStr(meta, cur), color: 'var(--text)' },
        { label: '24h change', value: c24.txt, color: col(c24) },
        { label: '7d change', value: c7.txt, color: col(c7) },
        { label: '30d change', value: c30.txt, color: col(c30) },
        { label: '52w low', value: IVAN.valStr(meta, lo), color: 'var(--text)' },
        { label: '52w high', value: IVAN.valStr(meta, hiv), color: 'var(--text)' },
        { label: '90d average', value: IVAN.valStr(meta, avg), color: 'var(--text)' },
        { label: 'Range position', value: pct + '%', color: 'var(--accent-strong)' },
      ];
      var about = {
        measures: meta.measures,
        method: meta.method,
        // Как индекс отражает поведение рынка и как читать его изменения —
        // приходят из indices/registry.py вместе с остальными метаданными.
        behaviour: meta.behaviour,
        reading: meta.reading,
        source: meta.source,
        url: meta.url,
        cat: tg.join(' · '),
        freq: 'Daily',
      };
      var chartEl = Charts.detailChart(React, {
        meta: meta,
        data: this.data,
        range: this.state.range,
        hover: this.state.hover,
        setHover: function (i) {
          self.setState({ hover: i });
        },
        cmpWith: this.state.cmpWith,
        alerts: this.state.alerts,
      });
      var gaugeEl = meta.gauge ? Charts.gauge(React, meta, cur) : null;
      return { d: d, stats: stats, about: about, gaugeEl: gaugeEl, chartEl: chartEl };
    }

    /** Список индексов после фильтра и сортировки */
    filteredItems() {
      var st = this.state;
      var I = this.data.indexes;
      var q = st.q.trim().toLowerCase();
      var list = I.filter(function (m) {
        var tg = IVAN.tagsOf(m);
        var catOk =
          st.cat === 'all'
            ? true
            : st.cat === 'saved'
              ? st.watch.indexOf(m.id) >= 0
              : tg.indexOf(st.cat) >= 0;
        return (
          catOk &&
          (!q || (m.name + ' ' + tg.join(' ') + ' ' + m.source).toLowerCase().indexOf(q) >= 0)
        );
      });
      if (st.sort === 'name') list.sort(function (a, b) {
        return a.name.localeCompare(b.name);
      });
      else if (st.sort === 'chg' || st.sort === 'chg24')
        list.sort(function (a, b) {
          return IVAN.relChg(b) - IVAN.relChg(a);
        });
      else if (st.sort === 'range')
        list.sort(function (a, b) {
          return IVAN.rangePos(b) - IVAN.rangePos(a);
        });
      return list;
    }

    enterTerminal() {
      var self = this;
      if (this.state.welcomeDismiss) IVAN.setWelcomeDismissed();
      this.setState({ welcomeExit: true });
      setTimeout(function () {
        self.setState({ welcomeOpen: false, welcomeExit: false, entering: true });
        if (self.page() === 'home') IVAN.restoreHomeScroll();
      }, 700);
      setTimeout(function () {
        self.setState({ entering: false });
      }, 1900);
    }

    cardMove(e) {
      var t = this._tip;
      if (!t) return;
      var overBtn = e.target && e.target.closest && e.target.closest('button');
      if (overBtn) {
        t.style.display = 'none';
        return;
      }
      t.style.display = 'block';
      t.style.left = e.clientX + 16 + 'px';
      t.style.top = e.clientY + 18 + 'px';
    }

    cardLeave() {
      if (this._tip) this._tip.style.display = 'none';
    }

    renderCard(c, opts) {
      var self = this;
      opts = opts || {};
      var compact = opts.compact;
      var onOpen = function () {
        self.openIndex(c.id);
      };
      var tagButtons = c.tags.map(function (label) {
        return h(
          'button',
          {
            key: label,
            'data-tagbtn': '1',
            title: 'Filter by this tag',
            style: ps(
              "font:600 8.5px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.11em;color:var(--text-dim);background:var(--layer);border:none;padding:4px 8px;border-radius:999px;white-space:nowrap;cursor:pointer;"
            ),
            onClick: function (e) {
              e.stopPropagation();
              self.applyFilter(label);
            },
          },
          label
        );
      });

      if (compact) {
        return h(
          'div',
          {
            key: c.id,
            onClick: onOpen,
            onMouseMove: function (e) {
              self.cardMove(e);
            },
            onMouseLeave: function () {
              self.cardLeave();
            },
            style: ps(
              'cursor:pointer;background:var(--bg2);border-radius:24px 24px 24px 6px;padding:18px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;transition:border-radius .3s,transform .2s,box-shadow .25s;'
            ),
          },
          h(
            'div',
            { style: { minWidth: 0 } },
            h(
              'div',
              {
                style: ps(
                  "font:600 8.5px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.11em;color:var(--text-faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                ),
              },
              c.tagsStr
            ),
            h(
              'div',
              {
                style: {
                  fontFamily: 'Newsreader',
                  fontSize: 17,
                  fontWeight: 500,
                  color: 'var(--text)',
                  marginTop: 4,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                },
              },
              c.name
            ),
            h(
              'div',
              { style: { display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 } },
              h(
                'span',
                {
                  style: ps("font:600 18px/1 'IBM Plex Mono';color:var(--text);"),
                },
                c.valueStr
              ),
              h('span', { style: { font: "500 11px 'IBM Plex Mono'", color: c.chg24Color } }, c.chg24)
            )
          ),
          h('div', { style: { flexShrink: 0 } }, c.sparkSm)
        );
      }

      return h(
        'div',
        {
          key: c.id,
          ref: function (el) {
            if (c.cardIndex != null) self._cards[c.cardIndex] = el;
          },
          onClick: onOpen,
          onMouseMove: function (e) {
            self.cardMove(e);
          },
          onMouseLeave: function () {
            self.cardLeave();
          },
          style: mergeStyle(
            'cursor:pointer;background:var(--bg2);border-radius:24px 24px 24px 6px;padding:20px 21px;display:flex;flex-direction:column;gap:14px;transition:border-radius .3s,transform .2s,box-shadow .25s;',
            c.span
          ),
        },
        h(
          'div',
          {
            style: {
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: 8,
            },
          },
          h(
            'div',
            null,
            h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 5 } }, tagButtons),
            h(
              'div',
              {
                style: {
                  fontFamily: 'Newsreader',
                  fontSize: 19,
                  fontWeight: 500,
                  color: 'var(--text)',
                  marginTop: 5,
                },
              },
              c.name
            )
          ),
          h(
            'div',
            { style: { display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 } },
            h(
              'span',
              {
                style: ps(
                  "display:inline-flex;align-items:center;gap:5px;font:600 9px 'IBM Plex Mono';letter-spacing:.12em;color:var(--up);background:var(--up-soft);padding:5px 9px;border-radius:999px;"
                ),
              },
              h('span', {
                style: {
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: 'var(--up)',
                  animation: 'ivpulse 2s infinite',
                },
              }),
              c.statusLabel
            ),
            h(
              'button',
              {
                style: ps(c.starStyle),
                title: 'Save to watchlist',
                onClick: function (e) {
                  e.stopPropagation();
                  self.toggleWatch(c.id);
                },
              },
              c.starIcon
            ),
            h(
              'button',
              {
                style: ps(c.cmpStyle),
                title: 'Add to compare',
                onClick: function (e) {
                  e.stopPropagation();
                  self.toggleCompare(c.id);
                },
              },
              c.cmpIcon
            )
          )
        ),
        h(
          'div',
          {
            style: {
              display: 'flex',
              alignItems: 'flex-end',
              justifyContent: 'space-between',
              gap: 10,
            },
          },
          h(
            'div',
            null,
            h('div', { style: ps("font:600 30px/1 'IBM Plex Mono';color:var(--text);") }, c.valueStr),
            h(
              'div',
              {
                style: {
                  fontSize: 11.5,
                  fontFamily: 'Archivo',
                  color: c.zoneColor,
                  marginTop: 6,
                  fontWeight: 600,
                },
              },
              c.zoneLabel
            )
          ),
          c.spark
        ),
        h(
          'div',
          {
            style: {
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderTop: '1px solid var(--hairline)',
              paddingTop: 12,
            },
          },
          h(
            'div',
            { style: { display: 'flex', gap: 12, font: "500 11px 'IBM Plex Mono'" } },
            h('span', { style: { color: 'var(--text-faint)' } }, '24h ', h('span', { style: { color: c.chg24Color } }, c.chg24)),
            h('span', { style: { color: 'var(--text-faint)' } }, '7d ', h('span', { style: { color: c.chg7Color } }, c.chg7))
          ),
          h('span', { style: { fontSize: 11, fontFamily: 'Archivo', color: 'var(--text-faint)' } }, c.source)
        )
      );
    }

    renderSidebar(st, I, items) {
      var self = this;
      var watchItems = st.watch
        .map(function (id) {
          return I.find(function (m) {
            return m.id === id;
          });
        })
        .filter(Boolean);

      var alertList = Object.keys(st.alerts)
        .map(function (id) {
          var m = I.find(function (x) {
            return x.id === id;
          });
          if (!m) return null;
          var a = st.alerts[id];
          var trig = IVAN.alertTriggered(m, a);
          return { m: m, a: a, trig: trig };
        })
        .filter(Boolean);

      var doms = [];
      var subs = [];
      var ctys = [];
      I.forEach(function (m) {
        var d = m.domain || 'Crypto';
        var s = m.sub || m.cat;
        var c = m.country;
        if (doms.indexOf(d) < 0) doms.push(d);
        if (subs.indexOf(s) < 0) subs.push(s);
        if (c && ctys.indexOf(c) < 0) ctys.push(c);
      });

      var tags = [{ t: 'all', label: 'All', count: I.length }, { t: 'saved', label: '★ Saved', count: st.watch.length }]
        .concat(doms.map(function (t) {
          return { t: t, label: t };
        }))
        .concat(
          subs.map(function (t) {
            return { t: t, label: t };
          })
        )
        .concat(
          ctys.map(function (t) {
            return { t: t, label: t };
          })
        );

      var tickerRows = [0, 1].map(function (k) {
        var m = I[(st.tickIdx + k) % I.length];
        var s = m.series;
        var ch = IVAN.fmtChange(m, s[s.length - 1], s[s.length - 2]);
        return {
          name: m.name,
          value: IVAN.valStr(m, s[s.length - 1]),
          chg: ch.txt,
          chgColor: ch.up ? 'var(--up)' : 'var(--down)',
        };
      });

      var asideStyle = ps(
        'position:fixed;left:0;top:0;z-index:60;height:100vh;display:flex;flex-direction:column;background:var(--bg);border-right:1px solid var(--hairline);transition:width .25s,padding .25s;width:' +
          (st.collapsed ? '64px' : '248px') +
          ';padding:' +
          (st.collapsed ? '20px 12px 18px' : '26px 18px 22px') +
          ';'
      );

      var expanded = !st.collapsed;

      return h(
        'aside',
        { style: asideStyle },
        expanded
          ? [
              h(
                'div',
                {
                  key: 'brand',
                  style: {
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 8,
                  },
                },
                h(
                  'div',
                  {
                    style: { cursor: 'pointer', padding: '0 0 0 14px' },
                    onClick: function () {
                      IVAN.goHome();
                    },
                  },
                  h(
                    'div',
                    {
                      style: {
                        fontFamily: 'Newsreader',
                        fontStyle: 'italic',
                        fontWeight: 500,
                        fontSize: 30,
                        color: 'var(--text)',
                      },
                    },
                    'IVAN'
                  ),
                  h(
                    'div',
                    {
                      style: ps(
                        "font:500 9px/1.7 'IBM Plex Mono';color:var(--text-faint);letter-spacing:.14em;text-transform:uppercase;margin-top:4px;"
                      ),
                    },
                    'Index · Volatility ·',
                    h('br'),
                    'Alerts · Notifications'
                  )
                ),
                h(
                  'button',
                  {
                    title: 'Collapse panel',
                    style: ps(
                      'width:28px;height:28px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid var(--hairline);background:transparent;color:var(--text-dim);font-size:13px;cursor:pointer;'
                    ),
                    onClick: function () {
                      self.setState({ collapsed: !st.collapsed });
                    },
                  },
                  '«'
                )
              ),
              h(
                'div',
                {
                  key: 'tick',
                  style: {
                    margin: '20px 14px 0',
                    height: 46,
                    overflow: 'hidden',
                    borderTop: '1px solid var(--hairline)',
                    borderBottom: '1px solid var(--hairline)',
                    cursor: 'pointer',
                  },
                  onMouseEnter: function () {
                    self._tickPaused = true;
                  },
                  onMouseLeave: function () {
                    self._tickPaused = false;
                  },
                  onClick: function () {
                    self.openIndex(I[st.tickIdx % I.length].id);
                  },
                },
                h(
                  'div',
                  {
                    style: ps(
                      'display:flex;flex-direction:column;transform:translateY(' +
                        (st.tickOff ? '-46px' : '0px') +
                        ');transition:' +
                        (st.tickAnim ? 'transform .55s cubic-bezier(.65,0,.25,1)' : 'none') +
                        ';'
                    ),
                  },
                  tickerRows.map(function (tk, idx) {
                    return h(
                      'div',
                      {
                        key: idx,
                        style: {
                          height: 46,
                          flexShrink: 0,
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'center',
                          gap: 4,
                        },
                      },
                      h(
                        'div',
                        {
                          style: ps(
                            "font:600 9px 'IBM Plex Mono';letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                          ),
                        },
                        tk.name
                      ),
                      h(
                        'div',
                        { style: { display: 'flex', gap: 8, font: "500 11.5px/1 'IBM Plex Mono'" } },
                        h('span', { style: { color: 'var(--text)' } }, tk.value),
                        h('span', { style: { color: tk.chgColor } }, tk.chg)
                      )
                    );
                  })
                )
              ),
              h(
                'div',
                { key: 'scroll', style: { flex: 1, overflowY: 'auto', minHeight: 0 } },
                h(
                  'button',
                  {
                    style: ps(
                      'width:calc(100% - 28px);margin:22px 14px 8px;display:flex;align-items:center;gap:8px;background:transparent;border:none;padding:0;cursor:pointer;'
                    ),
                    onClick: function () {
                      self.setState({ yoursOpen: st.yoursOpen === false });
                    },
                  },
                  h(
                    'span',
                    {
                      style: ps(
                        "font:600 9px 'IBM Plex Mono';letter-spacing:.18em;text-transform:uppercase;color:var(--text);"
                      ),
                    },
                    'Yours'
                  ),
                  h('div', { style: { flex: 1, height: 1, background: 'var(--hairline)' } }),
                  h(
                    'span',
                    {
                      style: ps(
                        "font:600 13px 'Archivo';line-height:1;color:var(--text-faint);transform:rotate(" +
                          (st.yoursOpen === false ? '0deg' : '90deg') +
                          ');transition:transform .25s cubic-bezier(.16,1,.3,1);'
                      ),
                    },
                    '›'
                  )
                ),
                st.yoursOpen !== false
                  ? h(
                      'div',
                      { key: 'yours', style: { padding: '0 14px' } },
                      h(
                        'div',
                        {
                          style: {
                            display: 'flex',
                            alignItems: 'baseline',
                            justifyContent: 'space-between',
                            gap: 8,
                          },
                        },
                        h(
                          'span',
                          {
                            style: ps(
                              "font:500 10px 'IBM Plex Mono';letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);"
                            ),
                          },
                          'Watchlist ',
                          st.watch.length
                        ),
                        st.watch.length
                          ? h(
                              'button',
                              {
                                style: ps(
                                  "border:none;background:transparent;color:var(--accent-strong);font:600 10px 'IBM Plex Mono';letter-spacing:.1em;text-transform:uppercase;cursor:pointer;padding:0;"
                                ),
                                onClick: function () {
                                  self.applyFilter('saved');
                                },
                              },
                              'only →'
                            )
                          : null
                      ),
                      !st.watch.length
                        ? h(
                            'div',
                            {
                              style: {
                                fontSize: 11,
                                fontFamily: 'Archivo',
                                color: 'var(--text-faint)',
                                lineHeight: 1.55,
                                marginTop: 6,
                              },
                            },
                            'Tap ☆ on any index to keep it here.'
                          )
                        : watchItems.map(function (m) {
                            var s = m.series;
                            var ch = IVAN.fmtChange(m, s[s.length - 1], s[s.length - 2]);
                            return h(
                              'div',
                              {
                                key: m.id,
                                style: {
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 8,
                                  padding: '8px 0',
                                  borderTop: '1px solid var(--hairline)',
                                  cursor: 'pointer',
                                },
                                onClick: function () {
                                  self.openIndex(m.id);
                                },
                              },
                              h(
                                'div',
                                { style: { flex: 1, minWidth: 0 } },
                                h(
                                  'div',
                                  {
                                    style: {
                                      fontSize: 11.5,
                                      fontFamily: 'Archivo',
                                      color: 'var(--text)',
                                      whiteSpace: 'nowrap',
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                    },
                                  },
                                  m.name
                                ),
                                h(
                                  'div',
                                  {
                                    style: {
                                      display: 'flex',
                                      gap: 7,
                                      font: "500 10.5px 'IBM Plex Mono'",
                                      marginTop: 2,
                                    },
                                  },
                                  h('span', { style: { color: 'var(--text-dim)' } }, IVAN.valStr(m, s[s.length - 1])),
                                  h('span', { style: { color: ch.up ? 'var(--up)' : 'var(--down)' } }, ch.txt)
                                )
                              ),
                              h(
                                'button',
                                {
                                  title: 'Remove',
                                  style: ps(
                                    'width:20px;height:20px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:none;background:transparent;color:var(--text-faint);font-size:12px;cursor:pointer;'
                                  ),
                                  onClick: function (e) {
                                    e.stopPropagation();
                                    self.toggleWatch(m.id);
                                  },
                                },
                                '×'
                              )
                            );
                          }),
                      alertList.length
                        ? [
                            h(
                              'div',
                              {
                                key: 'alh',
                                style: ps(
                                  "font:500 10px 'IBM Plex Mono';letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);margin:18px 14px 0;"
                                ),
                              },
                              'Alerts'
                            ),
                            h(
                              'div',
                              { key: 'als', style: { padding: '0 14px' } },
                              alertList.map(function (row) {
                                return h(
                                  'div',
                                  {
                                    key: row.m.id,
                                    style: {
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: 8,
                                      padding: '8px 0',
                                      borderTop: '1px solid var(--hairline)',
                                      cursor: 'pointer',
                                    },
                                    onClick: function () {
                                      self.openIndex(row.m.id);
                                    },
                                  },
                                  h(
                                    'div',
                                    { style: { flex: 1, minWidth: 0 } },
                                    h(
                                      'div',
                                      {
                                        style: {
                                          fontSize: 11.5,
                                          fontFamily: 'Archivo',
                                          color: 'var(--text)',
                                          whiteSpace: 'nowrap',
                                          overflow: 'hidden',
                                          textOverflow: 'ellipsis',
                                        },
                                      },
                                      row.m.name
                                    ),
                                    h(
                                      'div',
                                      {
                                        style: {
                                          font: "500 10.5px 'IBM Plex Mono'",
                                          color: 'var(--text-dim)',
                                          marginTop: 2,
                                        },
                                      },
                                      (row.a.op === 'below' ? '<' : '>') + ' ' + IVAN.fmt(row.a.value, row.m.dec)
                                    )
                                  ),
                                  h(
                                    'span',
                                    {
                                      style: ps(
                                        "font:600 8.5px 'IBM Plex Mono';letter-spacing:.1em;padding:3px 7px;border-radius:999px;flex-shrink:0;background:" +
                                          (row.trig ? 'var(--down)' : 'var(--layer)') +
                                          ';color:' +
                                          (row.trig ? 'var(--bg2)' : 'var(--text-faint)') +
                                          ';'
                                      ),
                                    },
                                    row.trig ? 'TRIGGERED' : 'ARMED'
                                  ),
                                  h(
                                    'button',
                                    {
                                      title: 'Remove alert',
                                      style: ps(
                                        'width:20px;height:20px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:none;background:transparent;color:var(--text-faint);font-size:12px;cursor:pointer;'
                                      ),
                                      onClick: function (e) {
                                        e.stopPropagation();
                                        self.removeAlert(row.m.id);
                                      },
                                    },
                                    '×'
                                  )
                                );
                              })
                            ),
                          ]
                        : null
                    )
                  : null,
                h(
                  'button',
                  {
                    key: 'browse-h',
                    style: ps(
                      'width:calc(100% - 28px);margin:26px 14px 10px;display:flex;align-items:center;gap:8px;background:transparent;border:none;padding:0;cursor:pointer;'
                    ),
                    onClick: function () {
                      self.setState({ browseOpen: st.browseOpen === false });
                    },
                  },
                  h(
                    'span',
                    {
                      style: ps(
                        "font:600 9px 'IBM Plex Mono';letter-spacing:.18em;text-transform:uppercase;color:var(--text);"
                      ),
                    },
                    'Browse'
                  ),
                  h('div', { style: { flex: 1, height: 1, background: 'var(--hairline)' } }),
                  h(
                    'span',
                    {
                      style: ps(
                        "font:600 13px 'Archivo';line-height:1;color:var(--text-faint);transform:rotate(" +
                          (st.browseOpen === false ? '0deg' : '90deg') +
                          ');transition:transform .25s cubic-bezier(.16,1,.3,1);'
                      ),
                    },
                    '›'
                  )
                ),
                st.browseOpen !== false
                  ? h(
                      'div',
                      { key: 'browse' },
                      h(
                        'div',
                        {
                          style: ps(
                            "font:500 10px 'IBM Plex Mono';letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);margin:0 14px 8px;"
                          ),
                        },
                        'Filter by tag'
                      ),
                      h(
                        'div',
                        { style: { display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 14px' } },
                        tags.map(function (o) {
                          var count =
                            o.count != null
                              ? o.count
                              : I.filter(function (m) {
                                  return IVAN.tagsOf(m).indexOf(o.t) >= 0;
                                }).length;
                          return h(
                            'button',
                            {
                              key: o.t,
                              style: ps(self.tagStyle(st.cat === o.t)),
                              onClick: function () {
                                self.applyFilter(o.t);
                              },
                            },
                            o.label,
                            h(
                              'span',
                              {
                                style: {
                                  marginLeft: 5,
                                  font: "500 9.5px 'IBM Plex Mono'",
                                  opacity: 0.65,
                                },
                              },
                              count
                            )
                          );
                        })
                      ),
                      h(
                        'div',
                        {
                          style: ps(
                            "font:500 10px 'IBM Plex Mono';letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);margin:18px 14px 8px;"
                          ),
                        },
                        'View'
                      ),
                      h(
                        'div',
                        {
                          style: {
                            display: 'flex',
                            background: 'var(--bg2)',
                            borderRadius: 999,
                            padding: 4,
                            gap: 2,
                            margin: '0 14px',
                          },
                        },
                        h(
                          'button',
                          {
                            style: ps(self.segStyle(st.layout === 'grid')),
                            onClick: function () {
                              self.setLayout('grid');
                            },
                          },
                          'Cards'
                        ),
                        h(
                          'button',
                          {
                            style: ps(self.segStyle(st.layout === 'table')),
                            onClick: function () {
                              self.setLayout('table');
                            },
                          },
                          'Table'
                        )
                      )
                    )
                  : null,
                h(
                  'div',
                  {
                    key: 'shortcuts',
                    style: ps(
                      "font:500 10px 'IBM Plex Mono';letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);margin:22px 14px 8px;"
                    ),
                  },
                  'Shortcuts'
                ),
                h(
                  'div',
                  {
                    style: {
                      padding: '0 14px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 5,
                      font: "500 10px 'IBM Plex Mono'",
                      color: 'var(--text-faint)',
                    },
                  },
                  h('div', null, '/ · search'),
                  h('div', null, '↑↓ · navigate · ⏎ open'),
                  h('div', null, 's · save · w · watchlist · esc · back')
                )
              ),
              h(
                'div',
                { key: 'theme', style: { display: 'flex', flexDirection: 'column', gap: 8, padding: '14px 14px 0' } },
                h(
                  'button',
                  {
                    style: ps(
                      "height:36px;display:inline-flex;align-items:center;justify-content:center;gap:8px;border-radius:999px;border:1px solid var(--hairline);background:transparent;color:var(--text-dim);font:500 12px 'Archivo';cursor:pointer;"
                    ),
                    onClick: function () {
                      self.setState({ theme: st.theme === 'dark' ? 'light' : 'dark' });
                    },
                  },
                  st.theme === 'dark' ? '☀' : '☾',
                  ' Theme'
                )
              ),
            ]
          : h(
              'div',
              {
                style: {
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 12,
                  height: '100%',
                },
              },
              h(
                'button',
                {
                  title: 'Expand panel',
                  style: ps(
                    'width:32px;height:32px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid var(--hairline);background:transparent;color:var(--text-dim);font-size:13px;cursor:pointer;'
                  ),
                  onClick: function () {
                    self.setState({ collapsed: false });
                  },
                },
                '»'
              ),
              h(
                'div',
                {
                  onClick: function () {
                    IVAN.goHome();
                  },
                  title: 'IVAN — home',
                  style: {
                    cursor: 'pointer',
                    fontFamily: 'Newsreader',
                    fontStyle: 'italic',
                    fontWeight: 500,
                    fontSize: 19,
                    color: 'var(--text)',
                    writingMode: 'sideways-lr',
                    letterSpacing: '.08em',
                    padding: '6px 0',
                  },
                },
                'IVAN'
              ),
              h('div', { style: { width: 20, height: 1, background: 'var(--hairline)' } }),
              h(
                'button',
                {
                  title: 'Theme',
                  style: ps(
                    'width:32px;height:32px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid var(--hairline);background:transparent;color:var(--text-dim);font-size:14px;cursor:pointer;'
                  ),
                  onClick: function () {
                    self.setState({ theme: st.theme === 'dark' ? 'light' : 'dark' });
                  },
                },
                st.theme === 'dark' ? '☀' : '☾'
              )
            )
      );
    }

    renderHomeMain(st, items) {
      var self = this;
      var count = items.length;

      var bandWins = [0, 1, 2].map(function (k) {
        var n = items.length;
        var dress = function (it) {
          return Object.assign({}, it, {
            bandChgColor: it.chg24Color === 'var(--up)' ? 'var(--band-up)' : 'var(--band-down)',
          });
        };
        if (n <= 3) return { rows: k < n ? [dress(items[k])] : [] };
        return {
          rows: [items[(st.tickIdx + k) % n], items[(st.tickIdx + k + 1) % n]].map(dress),
        };
      });

      var bandRollStyle =
        count <= 3
          ? 'display:flex;flex-direction:column;'
          : 'display:flex;flex-direction:column;transform:translateY(' +
            (st.tickOff ? '-116px' : '0px') +
            ');transition:' +
            (st.tickAnim ? 'transform .55s cubic-bezier(.65,0,.25,1)' : 'none') +
            ';';

      var sorts = [
        { id: 'featured', label: 'Featured' },
        { id: 'name', label: 'Name' },
        { id: 'chg', label: '24h Δ' },
        { id: 'range', label: 'Range' },
      ].map(function (s) {
        return h(
          'button',
          {
            key: s.id,
            style: ps(self.rangeStyle(st.sort === s.id)),
            onClick: function () {
              self.setState({ sort: s.id });
            },
          },
          s.label
        );
      });

      return h(
        'main',
        { style: { maxWidth: 1120, margin: '0 auto', padding: '46px 40px 90px' } },
        h(
          'div',
          {
            style: {
              display: 'flex',
              alignItems: 'flex-end',
              justifyContent: 'space-between',
              gap: 24,
              flexWrap: 'wrap',
            },
          },
          h(
            'div',
            null,
            h(
              'h1',
              {
                style: {
                  margin: 0,
                  fontFamily: 'Newsreader',
                  fontSize: 46,
                  fontWeight: 500,
                  letterSpacing: '-.015em',
                  lineHeight: 1.05,
                  color: 'var(--text)',
                },
              },
              'Market indexes, one ',
              h(
                'em',
                {
                  style: {
                    fontStyle: 'italic',
                    background: 'linear-gradient(transparent 62%, var(--tone-soft) 62%)',
                    padding: '0 2px',
                  },
                },
                'clean terminal'
              ),
              '.'
            ),
            h(
              'p',
              {
                style: {
                  margin: '14px 0 0',
                  fontSize: 14,
                  fontFamily: 'Archivo',
                  color: 'var(--text-dim)',
                  maxWidth: 520,
                  lineHeight: 1.6,
                },
              },
              'Crypto, equities, commodities, FX and macro indexes across countries — aggregated from open data, charted and ready to scan.'
            )
          ),
          h(
            'div',
            { style: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 12 } },
            h(
              'div',
              {
                style: ps(
                  "font:500 10.5px/1.8 'IBM Plex Mono';color:var(--text-faint);text-align:right;letter-spacing:.06em;"
                ),
              },
              'DAILY · OPEN DATA · ',
              count,
              ' INDEXES LIVE'
            ),
            h('input', {
              ref: function (el) {
                self._search = el;
              },
              value: st.q,
              onChange: function (e) {
                self.setState({ q: e.target.value });
              },
              placeholder: 'Search indexes, sources…',
              style: ps(
                "height:40px;width:280px;background:var(--bg2);border:1px solid transparent;border-radius:999px;padding:0 18px;color:var(--text);font-size:13px;font-family:'Archivo';outline:none;"
              ),
            })
          )
        ),
        h(
          'div',
          {
            style: {
              display: 'grid',
              gridTemplateColumns: '1fr 1fr 1fr 1fr',
              margin: '32px 0 0',
              background: 'var(--band)',
              borderRadius: '28px 28px 28px 6px',
              overflow: 'hidden',
            },
            onMouseEnter: function () {
              self._tickPaused = true;
            },
            onMouseLeave: function () {
              self._tickPaused = false;
            },
          },
          bandWins.map(function (bw, wi) {
            return h(
              'div',
              {
                key: wi,
                style: {
                  height: 116,
                  overflow: 'hidden',
                  borderLeft: '1px solid var(--band-line)',
                },
              },
              h(
                'div',
                { style: ps(bandRollStyle) },
                bw.rows.map(function (row, ri) {
                  return h(
                    'div',
                    {
                      key: ri,
                      onClick: function () {
                        self.openIndex(row.id);
                      },
                      style: {
                        height: 116,
                        flexShrink: 0,
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        gap: 6,
                        padding: '0 24px',
                        cursor: 'pointer',
                      },
                    },
                    h(
                      'div',
                      {
                        style: ps(
                          "font:600 9px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.14em;color:var(--band-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                        ),
                      },
                      row.tagsStr
                    ),
                    h(
                      'div',
                      {
                        style: {
                          fontFamily: 'Newsreader',
                          fontSize: 17,
                          fontWeight: 500,
                          color: 'var(--band-text)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        },
                      },
                      row.name
                    ),
                    h(
                      'div',
                      {
                        style: {
                          display: 'flex',
                          alignItems: 'baseline',
                          gap: 10,
                          font: "600 20px/1 'IBM Plex Mono'",
                          color: 'var(--tone)',
                        },
                      },
                      row.valueStr,
                      h(
                        'span',
                        { style: { font: "500 11px 'IBM Plex Mono'", color: row.bandChgColor } },
                        row.chg24
                      )
                    )
                  );
                })
              )
            );
          }),
          h(
            'div',
            {
              style: {
                height: 116,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                gap: 6,
                padding: '0 24px',
                borderLeft: '1px solid var(--band-line)',
              },
            },
            h(
              'div',
              {
                style: ps(
                  "font:600 9px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.14em;color:var(--band-dim);"
                ),
              },
              'Indexes live'
            ),
            h(
              'div',
              { style: ps("font:600 34px/1 'IBM Plex Mono';color:var(--band-text);") },
              count
            ),
            h(
              'div',
              { style: { fontSize: 11, fontFamily: 'Archivo', color: 'var(--band-dim)' } },
              'in current filter'
            )
          )
        ),
        h(
          'div',
          { style: { display: 'flex', alignItems: 'center', gap: 12, margin: '34px 0 20px' } },
          h(
            'span',
            { style: { fontFamily: 'Newsreader', fontSize: 22, fontWeight: 500, color: 'var(--text)' } },
            'All indexes'
          ),
          h('span', { style: ps("font:500 10.5px 'IBM Plex Mono';color:var(--text-faint);letter-spacing:.1em;") }, count),
          st.cat !== 'all'
            ? h(
                'button',
                {
                  style: ps(
                    "display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 11px;border-radius:999px;border:none;background:var(--accent);color:var(--on-accent);font:600 11px 'Archivo';cursor:pointer;"
                  ),
                  onClick: function () {
                    self.applyFilter('all');
                  },
                },
                st.cat === 'saved' ? '★ Saved' : st.cat,
                ' ×'
              )
            : null,
          h('div', { style: { flex: 1, height: 1, background: 'var(--hairline)' } }),
          h(
            'span',
            {
              style: ps(
                "font:600 9px 'IBM Plex Mono';letter-spacing:.16em;color:var(--text-faint);text-transform:uppercase;"
              ),
            },
            'Sort'
          ),
          h(
            'div',
            { style: { display: 'flex', background: 'var(--bg2)', borderRadius: 999, padding: 4, gap: 2 } },
            sorts
          )
        ),
        st.layout === 'grid'
          ? h(
              'div',
              { style: { display: 'grid', gridTemplateColumns: 'repeat(3,minmax(0,1fr))', gap: 16 } },
              items.map(function (c) {
                return self.renderCard(c);
              }),
              h(
                'div',
                {
                  onClick: function () {
                    self.setState({ reqOpen: true, reqSent: false });
                  },
                  style: ps(
                    'cursor:pointer;background:transparent;border:1.5px dashed var(--border-s);border-radius:24px 24px 24px 6px;padding:20px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;min-height:180px;'
                  ),
                },
                h(
                  'span',
                  {
                    style: ps(
                      "width:44px;height:44px;border-radius:50%;background:var(--accent);color:var(--on-accent);display:inline-flex;align-items:center;justify-content:center;font:600 22px/1 'Archivo';"
                    ),
                  },
                  '+'
                ),
                h(
                  'div',
                  {
                    style: {
                      fontFamily: 'Newsreader',
                      fontSize: 17,
                      fontWeight: 500,
                      color: 'var(--text)',
                    },
                  },
                  'Request an index'
                ),
                h(
                  'div',
                  {
                    style: {
                      fontSize: 11.5,
                      color: 'var(--text-faint)',
                      textAlign: 'center',
                      fontFamily: 'Archivo',
                      maxWidth: 200,
                      lineHeight: 1.5,
                    },
                  },
                  'Tell us which index you miss — we will add it to the terminal.'
                )
              )
            )
          : h(
              'div',
              {
                style: {
                  borderRadius: '24px 24px 24px 6px',
                  overflow: 'hidden',
                  background: 'var(--bg2)',
                },
              },
              h(
                'table',
                { style: { width: '100%', borderCollapse: 'collapse', fontSize: 13, fontFamily: 'Archivo' } },
                h(
                  'thead',
                  null,
                  h(
                    'tr',
                    { style: { background: 'var(--band)' } },
                    ['Index', 'Source', 'Value', '24h', '7d', '30d', '30d trend', 'Status'].map(function (lbl, i) {
                      return h(
                        'th',
                        {
                          key: lbl,
                          style: mergeStyle(
                            "padding:13px 18px;font:600 9.5px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.15em;color:var(--band-dim);",
                            i >= 2 && i <= 5 ? 'text-align:right;' : i >= 6 ? 'text-align:center;' : 'text-align:left;'
                          ),
                        },
                        lbl
                      );
                    })
                  )
                ),
                h(
                  'tbody',
                  null,
                  items.map(function (c) {
                    return h(
                      'tr',
                      {
                        key: c.id,
                        onClick: function () {
                          self.openIndex(c.id);
                        },
                        style: { cursor: 'pointer', borderTop: '1px solid var(--hairline)' },
                      },
                      h(
                        'td',
                        { style: { padding: '14px 18px' } },
                        h(
                          'div',
                          {
                            style: {
                              fontFamily: 'Newsreader',
                              fontSize: 16,
                              fontWeight: 500,
                              color: 'var(--text)',
                            },
                          },
                          c.name
                        ),
                        h(
                          'div',
                          {
                            style: ps(
                              "font:500 10px 'IBM Plex Mono';letter-spacing:.08em;color:var(--text-faint);margin-top:3px;text-transform:uppercase;"
                            ),
                          },
                          c.tagsStr
                        )
                      ),
                      h('td', { style: { padding: '14px 18px', color: 'var(--text-dim)' } }, c.source),
                      h(
                        'td',
                        { style: { padding: '14px 18px', textAlign: 'right', fontFamily: 'IBM Plex Mono', fontWeight: 600 } },
                        c.valueStr,
                        h(
                          'div',
                          {
                            style: {
                              fontSize: 10.5,
                              fontFamily: 'Archivo',
                              fontWeight: 600,
                              color: c.zoneColor,
                              marginTop: 2,
                            },
                          },
                          c.zoneLabel
                        )
                      ),
                      h(
                        'td',
                        { style: { padding: '14px 18px', textAlign: 'right', fontFamily: 'IBM Plex Mono', color: c.chg24Color } },
                        c.chg24
                      ),
                      h(
                        'td',
                        { style: { padding: '14px 18px', textAlign: 'right', fontFamily: 'IBM Plex Mono', color: c.chg7Color } },
                        c.chg7
                      ),
                      h(
                        'td',
                        { style: { padding: '14px 18px', textAlign: 'right', fontFamily: 'IBM Plex Mono', color: c.chg30Color } },
                        c.chg30
                      ),
                      h(
                        'td',
                        { style: { padding: '14px 18px', textAlign: 'center' } },
                        h('div', { style: { display: 'inline-block' } }, c.sparkSm)
                      ),
                      h(
                        'td',
                        { style: { padding: '14px 18px', textAlign: 'center' } },
                        h(
                          'span',
                          { style: { display: 'inline-flex', alignItems: 'center', gap: 8 } },
                          c.statusLabel,
                          h(
                            'button',
                            {
                              style: ps(c.starStyle),
                              onClick: function (e) {
                                e.stopPropagation();
                                self.toggleWatch(c.id);
                              },
                            },
                            c.starIcon
                          ),
                          h(
                            'button',
                            {
                              style: ps(c.cmpStyle),
                              onClick: function (e) {
                                e.stopPropagation();
                                self.toggleCompare(c.id);
                              },
                            },
                            c.cmpIcon
                          )
                        )
                      )
                    );
                  })
                )
              )
            )
      );
    }

    renderDetail(st, dmeta, det) {
      var self = this;
      var d = det.d;
      var about = det.about;
      var ranges = ['30d', '90d', '180d', '1y'].map(function (rg) {
        return h(
          'button',
          {
            key: rg,
            style: ps(self.rangeStyle(st.range === rg)),
            onClick: function () {
              self.setState({ range: rg, hover: null });
            },
          },
          rg === '1y' ? '1Y' : rg
        );
      });

      var cq = (st.cmpQuery || '').trim().toLowerCase();
      var cmpAll = [{ id: 'btc', label: 'BTC price', tag: 'market' }].concat(
        this.data.indexes
          .filter(function (m) {
            return !dmeta || m.id !== dmeta.id;
          })
          .map(function (m) {
            return { id: m.id, label: m.name, tag: m.domain || 'Index' };
          })
      );
      var cmpRes = cq
        ? cmpAll.filter(function (o) {
            return (o.label + ' ' + o.tag).toLowerCase().indexOf(cq) >= 0;
          })
        : cmpAll;
      this._cmpRes = cmpRes;

      var hasDetAlert = !!(dmeta && st.alerts[dmeta.id]);
      var detAlert = dmeta && st.alerts[dmeta.id];
      var detTrig = dmeta && detAlert && IVAN.alertTriggered(dmeta, detAlert);

      var relatedTag = dmeta ? dmeta.domain || 'Crypto' : '';
      var related = dmeta
        ? this.data.indexes
            .filter(function (m) {
              return m.id !== dmeta.id && (m.domain || 'Crypto') === relatedTag;
            })
            .slice(0, 3)
            .map(function (m, i) {
              return self.buildItem(m, false, null);
            })
        : [];

      var watched = dmeta && st.watch.indexOf(dmeta.id) >= 0;

      return h(
        'main',
        { style: { maxWidth: 1120, margin: '0 auto', padding: '30px 40px 90px' } },
        h(
          'div',
          { style: { display: 'flex', alignItems: 'center', gap: 10, margin: '24px 0 0' } },
          h(
            'button',
            {
              style: ps(
                "display:inline-flex;align-items:center;gap:7px;height:34px;padding:0 16px;border-radius:999px;border:1px solid var(--border-s);background:transparent;color:var(--text-dim);font:500 12px 'Archivo';cursor:pointer;"
              ),
              onClick: function () {
                IVAN.goHome();
              },
            },
            '← All indexes'
          ),
          h(
            'button',
            {
              style: ps(
                'display:inline-flex;align-items:center;gap:7px;height:34px;padding:0 16px;border-radius:999px;border:1px solid ' +
                  (watched ? 'var(--accent)' : 'var(--border-s)') +
                  ';background:' +
                  (watched ? 'var(--accent)' : 'transparent') +
                  ';color:' +
                  (watched ? 'var(--on-accent)' : 'var(--text-dim)') +
                  ";font:500 12px 'Archivo';cursor:pointer;"
              ),
              onClick: function () {
                if (dmeta) self.toggleWatch(dmeta.id);
              },
            },
            watched ? '★ Saved' : '☆ Save to watchlist'
          )
        ),
        h(
          'div',
          {
            style: {
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'flex-end',
              justifyContent: 'space-between',
              gap: 24,
              margin: '24px 0',
            },
          },
          h(
            'div',
            null,
            h(
              'div',
              {
                style: ps(
                  "font:600 10px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.16em;color:var(--text-faint);"
                ),
              },
              d.cat,
              ' · ',
              d.source
            ),
            h(
              'h1',
              {
                style: {
                  margin: '6px 0 0',
                  fontFamily: 'Newsreader',
                  fontSize: 40,
                  fontWeight: 500,
                  letterSpacing: '-.01em',
                  color: 'var(--text)',
                },
              },
              d.name
            )
          ),
          h(
            'div',
            { style: { display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' } },
            h(
              'div',
              { style: { display: 'flex', alignItems: 'baseline', gap: 12 } },
              h('span', { style: ps("font:600 42px/1 'IBM Plex Mono';color:var(--text);") }, d.valueStr),
              h(
                'span',
                { style: { fontSize: 13, fontFamily: 'Archivo', fontWeight: 600, color: d.zoneColor } },
                d.zoneLabel
              )
            ),
            h(
              'div',
              { style: { display: 'flex', gap: 8 } },
              ['24h', '7d', '30d'].map(function (lbl, i) {
                var key = ['c24', 'c7', 'c30'][i];
                var col = ['c24c', 'c7c', 'c30c'][i];
                return h(
                  'div',
                  {
                    key: lbl,
                    style: { background: 'var(--bg2)', borderRadius: 999, padding: '8px 14px' },
                  },
                  h('span', { style: ps("font:500 10px 'IBM Plex Mono';color:var(--text-faint);") }, lbl + ' '),
                  h('span', { style: ps("font:600 12px 'IBM Plex Mono';color:" + d[col] + ';') }, d[key])
                );
              })
            )
          )
        ),
        h(
          'div',
          {
            style: {
              background: 'var(--bg2)',
              borderRadius: '28px 28px 28px 6px',
              padding: '18px 20px',
              minWidth: 0,
            },
          },
          h(
            'div',
            {
              style: {
                display: 'flex',
                alignItems: 'center',
                gap: 18,
                flexWrap: 'wrap',
                marginBottom: 12,
              },
            },
            h(
              'div',
              { style: { display: 'flex', alignItems: 'center', gap: 7, fontSize: 11.5, fontFamily: 'Archivo', color: 'var(--text-dim)' } },
              h('span', {
                style: { width: 16, height: 3, borderRadius: 2, background: 'var(--accent)' },
              }),
              d.name
            ),
            h(
              'div',
              { style: { display: 'flex', alignItems: 'center', gap: 8, position: 'relative' } },
              h('span', {
                style: { width: 16, height: 0, borderTop: '2px dashed var(--text-faint)', flexShrink: 0 },
              }),
              h(
                'span',
                {
                  style: ps(
                    "font:600 9px 'IBM Plex Mono';letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);"
                  ),
                },
                'vs'
              ),
              h(
                'div',
                { style: { position: 'relative' } },
                h('input', {
                  value: st.cmpQuery,
                  placeholder: 'Add comparison…',
                  style: ps(
                    'height:28px;width:200px;background:var(--bg);border:1px solid ' +
                      (st.cmpOpen ? 'var(--accent)' : 'var(--hairline)') +
                      ";border-radius:999px;padding:0 26px 0 12px;color:var(--text);font:500 11.5px 'Archivo';outline:none;"
                  ),
                  onChange: function (e) {
                    self.setState({ cmpQuery: e.target.value, cmpOpen: true, cmpSel: 0 });
                  },
                  onFocus: function () {
                    self.setState({ cmpOpen: true, cmpSel: 0 });
                  },
                  onKeyDown: function (e) {
                    var r = self._cmpRes || [];
                    if (e.key === 'ArrowDown') {
                      e.preventDefault();
                      self.setState({ cmpOpen: true, cmpSel: Math.min(r.length - 1, (st.cmpSel || 0) + 1) });
                    } else if (e.key === 'ArrowUp') {
                      e.preventDefault();
                      self.setState({ cmpSel: Math.max(0, (st.cmpSel || 0) - 1) });
                    } else if (e.key === 'Enter') {
                      var p = r[st.cmpSel || 0];
                      if (p) {
                        e.preventDefault();
                        self.pickCmp(p.id, p.label);
                      }
                    } else if (e.key === 'Escape') {
                      e.stopPropagation();
                      self.setState({ cmpOpen: false });
                    }
                  },
                }),
                (st.cmpWith !== 'none' || st.cmpQuery)
                  ? h(
                      'button',
                      {
                        title: 'Clear',
                        style: ps(
                          'position:absolute;right:6px;top:50%;transform:translateY(-50%);width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:none;background:var(--layer);color:var(--text-dim);font-size:12px;cursor:pointer;'
                        ),
                        onClick: function () {
                          self.setState({ cmpWith: 'none', cmpQuery: '', cmpOpen: false, hover: null });
                        },
                      },
                      '×'
                    )
                  : null,
                st.cmpOpen
                  ? h(
                      'div',
                      {
                        style: ps(
                          'position:absolute;top:34px;left:0;width:262px;max-height:264px;overflow-y:auto;background:var(--bg2);border:1px solid var(--hairline);border-radius:16px 16px 16px 4px;box-shadow:0 20px 48px var(--shadow);padding:6px;z-index:40;'
                        ),
                      },
                      !cmpRes.length
                        ? h(
                            'div',
                            {
                              style: {
                                padding: '12px 10px',
                                fontSize: 11.5,
                                fontFamily: 'Archivo',
                                color: 'var(--text-faint)',
                              },
                            },
                            'No index matches “',
                            st.cmpQuery,
                            '”'
                          )
                        : cmpRes.map(function (o, i) {
                            return h(
                              'button',
                              {
                                key: o.id + o.label,
                                style: ps(
                                  'display:flex;align-items:center;gap:10px;width:100%;padding:9px 11px;border:none;border-radius:10px;background:' +
                                    ((st.cmpSel || 0) === i ? 'var(--layer)' : 'transparent') +
                                    ";color:var(--text);font:500 12px 'Archivo';cursor:pointer;text-align:left;"
                                ),
                                onClick: function () {
                                  self.pickCmp(o.id, o.label);
                                },
                                onMouseEnter: function () {
                                  self.setState({ cmpSel: i });
                                },
                              },
                              h(
                                'span',
                                {
                                  style: {
                                    flex: 1,
                                    minWidth: 0,
                                    textAlign: 'left',
                                    whiteSpace: 'nowrap',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                  },
                                },
                                o.label
                              ),
                              h(
                                'span',
                                {
                                  style: ps(
                                    "font:500 9px 'IBM Plex Mono';letter-spacing:.1em;text-transform:uppercase;color:var(--text-faint);flex-shrink:0;"
                                  ),
                                },
                                o.tag
                              )
                            );
                          })
                    )
                  : null
              )
            ),
            // Легенда объёма — только у индексов, привязанных к торгуемому рынку.
            // Подпись берём из метаданных: у ставки финансирования это оборот
            // бессрочного контракта, у остальных крипто-индексов — спота.
            dmeta.volume && dmeta.volumeLabel
              ? h(
                  'div',
                  {
                    style: {
                      display: 'flex',
                      alignItems: 'center',
                      gap: 7,
                      fontSize: 11.5,
                      fontFamily: 'Archivo',
                      color: 'var(--text-dim)',
                    },
                  },
                  h('span', {
                    style: {
                      width: 10,
                      height: 11,
                      background: 'var(--accent)',
                      opacity: 0.3,
                      borderRadius: 2,
                    },
                  }),
                  dmeta.volumeLabel
                )
              : null,
            h('div', { style: { flex: 1 } }),
            h(
              'div',
              { style: { display: 'flex', background: 'var(--bg)', borderRadius: 999, padding: 4, gap: 2 } },
              ranges
            )
          ),
          h('div', { style: { width: '100%' } }, det.chartEl)
        ),
        h(
          'div',
          {
            style: {
              display: 'grid',
              gridTemplateColumns: '1fr 340px',
              gap: 16,
              marginTop: 16,
              alignItems: 'start',
            },
          },
          h(
            'div',
            { style: { display: 'flex', flexDirection: 'column', gap: 16 } },
            h(
              'div',
              { style: { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 } },
              det.stats.map(function (s) {
                return h(
                  'div',
                  {
                    key: s.label,
                    style: {
                      background: 'var(--bg2)',
                      borderRadius: '16px 16px 16px 4px',
                      padding: '15px 17px',
                    },
                  },
                  h(
                    'div',
                    {
                      style: ps(
                        "font:600 9px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.14em;color:var(--text-faint);"
                      ),
                    },
                    s.label
                  ),
                  h(
                    'div',
                    {
                      style: {
                        font: "600 20px 'IBM Plex Mono'",
                        color: s.color,
                        marginTop: 8,
                      },
                    },
                    s.value
                  )
                );
              })
            ),
            h(
              'div',
              {
                style: {
                  background: 'var(--bg2)',
                  borderRadius: '24px 24px 24px 6px',
                  padding: '24px 26px',
                },
              },
              h(
                'div',
                {
                  style: {
                    fontFamily: 'Newsreader',
                    fontSize: 21,
                    fontWeight: 500,
                    color: 'var(--text)',
                  },
                },
                'About this index'
              ),
              // Четыре раздела: что показывает, как считается, что говорит о
              // рынке и как читать изменения. Пустые поля пропускаем, чтобы
              // блок не разъезжался, если у индекса нет части описания.
              [
                { label: 'What it measures', text: about.measures, lead: true },
                { label: 'How it is calculated', text: about.method },
                { label: 'What it says about the market', text: about.behaviour },
                { label: 'How to read changes', text: about.reading },
              ]
                .filter(function (s) {
                  return !!s.text;
                })
                .map(function (s, i) {
                  return h(
                    'div',
                    { key: s.label, style: { marginTop: i === 0 ? 18 : 20 } },
                    h(
                      'div',
                      {
                        style: {
                          fontFamily: 'IBM Plex Mono',
                          fontSize: 9.5,
                          fontWeight: 500,
                          letterSpacing: '0.16em',
                          textTransform: 'uppercase',
                          color: 'var(--text-faint)',
                          marginBottom: 7,
                        },
                      },
                      s.label
                    ),
                    h(
                      'p',
                      {
                        style: {
                          fontSize: s.lead ? 13.5 : 12.5,
                          fontFamily: 'Archivo',
                          color: s.lead ? 'var(--text-dim)' : 'var(--text-faint)',
                          lineHeight: 1.7,
                          margin: 0,
                        },
                      },
                      s.text
                    )
                  );
                })
            )
          ),
          h(
            'div',
            { style: { display: 'flex', flexDirection: 'column', gap: 16 } },
            h(
              'div',
              {
                style: {
                  background: 'var(--bg2)',
                  borderRadius: '24px 24px 24px 6px',
                  padding: '22px 24px',
                },
              },
              h(
                'div',
                {
                  style: {
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'space-between',
                    gap: 10,
                  },
                },
                h(
                  'div',
                  {
                    style: {
                      fontFamily: 'Newsreader',
                      fontSize: 19,
                      fontWeight: 500,
                      color: 'var(--text)',
                    },
                  },
                  'Alert'
                ),
                hasDetAlert
                  ? h(
                      'span',
                      {
                        style: ps(
                          "font:600 9px 'IBM Plex Mono';letter-spacing:.12em;text-transform:uppercase;padding:4px 9px;border-radius:999px;background:" +
                            (detTrig ? 'var(--down)' : 'var(--up-soft)') +
                            ';color:' +
                            (detTrig ? 'var(--bg2)' : 'var(--up)') +
                            ';'
                        ),
                      },
                      detTrig ? 'Triggered now' : 'Armed · waiting'
                    )
                  : null
              ),
              h(
                'div',
                {
                  style: {
                    fontSize: 11.5,
                    fontFamily: 'Archivo',
                    color: 'var(--text-faint)',
                    marginTop: 4,
                    lineHeight: 1.55,
                  },
                },
                'Notify me when this index crosses my threshold.'
              ),
              h(
                'div',
                {
                  style: {
                    display: 'flex',
                    background: 'var(--bg)',
                    borderRadius: 999,
                    padding: 4,
                    gap: 2,
                    marginTop: 14,
                  },
                },
                h(
                  'button',
                  {
                    style: ps(self.rangeStyle(st.alertOp === 'below')),
                    onClick: function () {
                      self.setState({ alertOp: 'below' });
                    },
                  },
                  'Below'
                ),
                h(
                  'button',
                  {
                    style: ps(self.rangeStyle(st.alertOp === 'above')),
                    onClick: function () {
                      self.setState({ alertOp: 'above' });
                    },
                  },
                  'Above'
                )
              ),
              h('input', {
                value: st.alertVal,
                onChange: function (e) {
                  self.setState({ alertVal: e.target.value });
                },
                inputMode: 'decimal',
                placeholder: 'Threshold value',
                style: ps(
                  "margin-top:10px;width:100%;height:42px;background:var(--bg);border:1px solid var(--hairline);border-radius:12px;padding:0 14px;color:var(--text);font:600 14px 'IBM Plex Mono';outline:none;"
                ),
              }),
              h(
                'div',
                { style: { display: 'flex', gap: 8, marginTop: 10 } },
                h(
                  'button',
                  {
                    style: ps(
                      "flex:1;height:40px;border:none;border-radius:999px;background:var(--accent);color:var(--on-accent);font:600 12.5px 'Archivo';cursor:pointer;"
                    ),
                    onClick: function () {
                      if (dmeta) self.setAlert(dmeta.id);
                    },
                  },
                  hasDetAlert ? 'Update alert' : 'Set alert'
                ),
                hasDetAlert
                  ? h(
                      'button',
                      {
                        title: 'Remove alert',
                        style: ps(
                          'width:40px;height:40px;border:1px solid var(--border-s);border-radius:999px;background:transparent;color:var(--text-dim);font-size:14px;cursor:pointer;'
                        ),
                        onClick: function () {
                          if (dmeta) self.removeAlert(dmeta.id);
                        },
                      },
                      '×'
                    )
                  : null
              )
            ),
            h(
              'div',
              {
                style: {
                  background: 'var(--band)',
                  borderRadius: '28px 28px 6px 28px',
                  padding: 24,
                },
              },
              d.hasGauge
                ? [
                    h('div', { key: 'g', style: { width: '100%' } }, det.gaugeEl),
                    h(
                      'div',
                      {
                        key: 'gl',
                        style: {
                          fontSize: 14,
                          fontFamily: 'Archivo',
                          fontWeight: 600,
                          color: d.zoneColor,
                          textAlign: 'center',
                          marginTop: 2,
                        },
                      },
                      d.zoneLabel
                    ),
                    h(
                      'div',
                      {
                        key: 'gr',
                        style: {
                          fontSize: 11.5,
                          fontFamily: 'Archivo',
                          color: 'var(--band-dim)',
                          textAlign: 'center',
                          lineHeight: 1.6,
                          marginTop: 12,
                        },
                      },
                      d.reading
                    ),
                  ]
                : [
                    h(
                      'div',
                      {
                        key: 'ngl',
                        style: ps(
                          "font:600 9.5px 'IBM Plex Mono';text-transform:uppercase;letter-spacing:.16em;color:var(--band-dim);"
                        ),
                      },
                      'Current value'
                    ),
                    h(
                      'div',
                      {
                        key: 'ngv',
                        style: ps("font:600 48px/1 'IBM Plex Mono';color:var(--band-text);margin:12px 0 8px;"),
                      },
                      d.valueStr
                    ),
                    h(
                      'div',
                      {
                        key: 'ngz',
                        style: {
                          fontSize: 13,
                          fontFamily: 'Archivo',
                          fontWeight: 600,
                          color: d.zoneColor,
                        },
                      },
                      d.zoneLabel
                    ),
                    h(
                      'div',
                      {
                        key: 'ngr',
                        style: {
                          fontSize: 11.5,
                          fontFamily: 'Archivo',
                          color: 'var(--band-dim)',
                          lineHeight: 1.6,
                          marginTop: 16,
                        },
                      },
                      d.reading
                    ),
                  ]
            ),
            h(
              'div',
              {
                style: {
                  background: 'var(--bg2)',
                  borderRadius: '24px 24px 6px 24px',
                  padding: '22px 26px',
                },
              },
              ['Source', 'Category', 'Updated'].map(function (lbl, i) {
                var vals = [about.source, about.cat, about.freq];
                return h(
                  'div',
                  {
                    key: lbl,
                    style: {
                      display: 'flex',
                      justifyContent: 'space-between',
                      padding: '10px 0',
                      borderBottom: '1px solid var(--hairline)',
                      fontSize: 12.5,
                      fontFamily: 'Archivo',
                    },
                  },
                  h('span', { style: { color: 'var(--text-faint)' } }, lbl),
                  h('span', { style: { color: 'var(--text)', fontWeight: 500 } }, vals[i])
                );
              }),
              h(
                'a',
                {
                  href: about.url,
                  target: '_blank',
                  rel: 'noopener',
                  style: {
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    marginTop: 16,
                    fontSize: 12.5,
                    fontFamily: 'Archivo',
                    color: 'var(--text)',
                    textDecoration: 'none',
                    fontWeight: 600,
                  },
                },
                'Visit data source ↗'
              )
            )
          )
        ),
        related.length
          ? [
              h(
                'div',
                {
                  key: 'rh',
                  style: { display: 'flex', alignItems: 'center', gap: 12, margin: '34px 0 16px' },
                },
                h(
                  'span',
                  {
                    style: {
                      fontFamily: 'Newsreader',
                      fontSize: 21,
                      fontWeight: 500,
                      color: 'var(--text)',
                    },
                  },
                  'More in ',
                  relatedTag
                ),
                h('div', { style: { flex: 1, height: 1, background: 'var(--hairline)' } })
              ),
              h(
                'div',
                {
                  key: 'rg',
                  style: {
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3,minmax(0,1fr))',
                    gap: 16,
                  },
                },
                related.map(function (c) {
                  return self.renderCard(c, { compact: true });
                })
              ),
            ]
          : null
      );
    }

    renderNotFound() {
      return h(
        'main',
        { style: { maxWidth: 1120, margin: '0 auto', padding: '80px 40px', textAlign: 'center' } },
        h(
          'h1',
          {
            style: {
              fontFamily: 'Newsreader',
              fontSize: 36,
              fontWeight: 500,
              color: 'var(--text)',
              margin: 0,
            },
          },
          'Index not found'
        ),
        h(
          'p',
          {
            style: {
              fontFamily: 'Archivo',
              color: 'var(--text-dim)',
              marginTop: 16,
              lineHeight: 1.6,
            },
          },
          'This index id is not in the terminal catalog.'
        ),
        h(
          'button',
          {
            style: ps(
              "margin-top:24px;height:40px;padding:0 20px;border:none;border-radius:999px;background:var(--accent);color:var(--on-accent);font:600 13px 'Archivo';cursor:pointer;"
            ),
            onClick: function () {
              IVAN.goHome();
            },
          },
          '← Back to all indexes'
        )
      );
    }

    renderWelcome(st, I) {
      var self = this;
      var welcomeShellStyle = ps(
        'position:fixed;inset:0;z-index:200;background:var(--bg);display:flex;align-items:center;justify-content:center;overflow:hidden;' +
          (st.welcomeExit
            ? 'animation:ivwLift .68s .12s cubic-bezier(.7,0,.84,0) forwards;pointer-events:none;'
            : '')
      );
      var wVeilStyle = ps(
        'position:absolute;inset:0;overflow:hidden;pointer-events:none;transition:opacity .5s ease;' +
          (st.welcomeExit
            ? 'opacity:.9;-webkit-mask-image:none;mask-image:none;'
            : 'opacity:.2;-webkit-mask-image:radial-gradient(115% 78% at 50% 50%, transparent 26%, #000 72%),linear-gradient(#0000 0, #000 130px, #000 calc(100% - 70px), #0000 100%);mask-image:radial-gradient(115% 78% at 50% 50%, transparent 26%, #000 72%),linear-gradient(#0000 0, #000 130px, #000 calc(100% - 70px), #0000 100%);-webkit-mask-composite:source-in;mask-composite:intersect;')
      );
      var wGridStyle = ps(
        'position:absolute;inset:20px 40px -60px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0 56px;align-content:start;' +
          (st.welcomeExit
            ? 'animation:none;transform:scale(1.14);transition:transform .75s cubic-bezier(.16,1,.3,1);'
            : 'animation:ivwDrift 26s cubic-bezier(.4,0,.6,1) infinite alternate;')
      );

      var wRows = I.map(function (m, i) {
        var s = m.series;
        var ch = IVAN.fmtChange(m, s[s.length - 1], s[s.length - 2]);
        return h(
          'div',
          {
            key: m.id,
            style: ps(
              'display:flex;align-items:baseline;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid var(--hairline);font:500 11px IBM Plex Mono;color:var(--text-dim);opacity:0;animation:ivwFade 1.4s ' +
                (0.2 + i * 0.045).toFixed(2) +
                's forwards;'
            ),
          },
          h(
            'span',
            { style: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
            m.name
          ),
          h('span', { style: { color: ch.up ? 'var(--up)' : 'var(--down)' } }, ch.txt)
        );
      });

      var marquee = I.concat(I).map(function (m, i) {
        return h(
          'span',
          {
            key: i + m.id,
            style: {
              display: 'inline-flex',
              alignItems: 'center',
              gap: 14,
              padding: '0 20px',
              font: "500 10.5px 'IBM Plex Mono'",
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--text-faint)',
              whiteSpace: 'nowrap',
            },
          },
          m.name,
          h('span', {
            style: { width: 3, height: 3, borderRadius: '50%', background: 'var(--border-s)' },
          })
        );
      });

      return h(
        'div',
        { style: welcomeShellStyle },
        h('div', { style: wVeilStyle }, h('div', { style: wGridStyle }, wRows)),
        h(
          'div',
          {
            style: ps(
              'position:absolute;top:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;padding:30px 40px;animation:ivwFade .8s .15s both;transition:opacity .3s;' +
                (st.welcomeExit ? 'opacity:0;' : '')
            ),
          },
          h(
            'div',
            { style: { display: 'flex', alignItems: 'center', gap: 10 } },
            h('div', {
              style: {
                width: 9,
                height: 9,
                borderRadius: '50%',
                background: 'var(--accent)',
                animation: 'ivpulse 2.4s infinite',
              },
            }),
            h(
              'span',
              {
                style: ps(
                  "font:600 10px 'IBM Plex Mono';letter-spacing:.22em;text-transform:uppercase;color:var(--text);"
                ),
              },
              'IVAN'
            )
          ),
          h(
            'span',
            {
              style: ps(
                "font:500 10px 'IBM Plex Mono';letter-spacing:.2em;text-transform:uppercase;color:var(--text-faint);"
              ),
            },
            I.length,
            ' indexes · daily · open data'
          )
        ),
        h(
          'div',
          {
            style: ps(
              'position:relative;z-index:2;width:100%;max-width:920px;padding:0 32px;display:flex;flex-direction:column;align-items:center;text-align:center;' +
                (st.welcomeExit
                  ? 'animation:ivwCenterOut .38s cubic-bezier(.5,0,.9,.2) forwards;'
                  : '')
            ),
          },
          // Eyebrow: INDEX TERMINAL с линиями по бокам (как в Claude Design).
          h(
            'div',
            {
              style: {
                display: 'flex',
                alignItems: 'center',
                gap: 16,
                width: '100%',
                maxWidth: 560,
                animation: 'ivwFade 1s .3s both',
              },
            },
            h('div', {
              style: ps(
                'flex:1;height:1px;background:var(--hairline);transform-origin:right;animation:ivwLine 1.1s .35s cubic-bezier(.16,1,.3,1) both;'
              ),
            }),
            h(
              'span',
              {
                style: ps(
                  "font:600 9.5px 'IBM Plex Mono';letter-spacing:.24em;text-transform:uppercase;color:var(--text-faint);white-space:nowrap;"
                ),
              },
              'Index Terminal'
            ),
            h('div', {
              style: ps(
                'flex:1;height:1px;background:var(--hairline);transform-origin:left;animation:ivwLine 1.1s .35s cubic-bezier(.16,1,.3,1) both;'
              ),
            })
          ),
          // Главный заголовок welcome: «Ready for the bigger picture?»
          h(
            'h1',
            {
              style: {
                margin: '34px 0 0',
                fontFamily: 'Newsreader',
                fontWeight: 500,
                fontSize: 'clamp(46px,7vw,96px)',
                lineHeight: 1.02,
                letterSpacing: '-.025em',
                color: 'var(--text)',
              },
            },
            (function () {
              // Каждое слово в overflow-обёртке + ivwRise.
              // Между словами нужен явный пробел: React-массив детей НЕ вставляет
              // whitespace (в HTML-прототипе пробелы были между тегами).
              var words = [
                { t: 'Ready', delay: '.45s', em: false },
                { t: 'for', delay: '.56s', em: false },
                { t: 'the', delay: '.64s', em: false },
                { t: 'bigger', delay: '.72s', em: true },
                { t: 'picture', delay: '.8s', em: true, q: true },
              ];
              var nodes = [];
              words.forEach(function (w, i) {
                var inner = w.em
                  ? h(
                      'em',
                      {
                        style: {
                          fontStyle: 'italic',
                          background:
                            'linear-gradient(var(--tone-soft),var(--tone-soft)) 0 66% / 100% .34em no-repeat',
                          padding: '0 .04em',
                        },
                      },
                      w.t + (w.q ? '?' : '')
                    )
                  : w.t;
                nodes.push(
                  h(
                    'span',
                    {
                      key: w.t,
                      style: {
                        display: 'inline-block',
                        overflow: 'hidden',
                        verticalAlign: 'bottom',
                        padding: '0 .06em',
                        margin: '0 -.06em',
                      },
                    },
                    h(
                      'span',
                      {
                        style: {
                          display: 'inline-block',
                          animation:
                            'ivwRise 1s ' + w.delay + ' cubic-bezier(.16,1,.3,1) both',
                        },
                      },
                      inner
                    )
                  )
                );
                if (i < words.length - 1) nodes.push(' ');
              });
              return nodes;
            })()
          ),
          h(
            'button',
            {
              style: ps(
                "margin-top:46px;height:60px;padding:0 40px;display:inline-flex;align-items:center;gap:14px;border:none;border-radius:999px;background:var(--accent);color:var(--on-accent);font:600 16px 'Archivo';cursor:pointer;box-shadow:0 18px 44px var(--shadow);animation:ivwSweep .95s 1.05s cubic-bezier(.16,1,.3,1) both;"
              ),
              onClick: function () {
                self.enterTerminal();
              },
            },
            "Yes, I'm ready ",
            h('span', { style: { font: "500 17px 'IBM Plex Mono'" } }, '→')
          ),
          h(
            'label',
            {
              style: {
                marginTop: 26,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                cursor: 'pointer',
                userSelect: 'none',
                animation: 'ivwUp .9s 1.3s both',
              },
              onClick: function () {
                self.setState({ welcomeDismiss: !st.welcomeDismiss });
              },
            },
            h(
              'span',
              {
                style: ps(
                  'width:18px;height:18px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border-radius:6px;font:700 11px Archivo;border:1.5px solid ' +
                    (st.welcomeDismiss ? 'var(--accent)' : 'var(--border-s)') +
                    ';background:' +
                    (st.welcomeDismiss ? 'var(--accent)' : 'transparent') +
                    ';color:var(--on-accent);'
                ),
              },
              st.welcomeDismiss ? '✓' : ''
            ),
            h('span', { style: { font: "500 12.5px 'Archivo'", color: 'var(--text-dim)' } }, "Don't show again")
          )
        ),
        h(
          'div',
          {
            style: ps(
              'position:absolute;bottom:0;left:0;right:0;border-top:1px solid var(--hairline);padding:16px 0;overflow:hidden;animation:ivwUp 1s 1.45s both;transition:opacity .3s;' +
                (st.welcomeExit ? 'opacity:0;' : '')
            ),
          },
          h(
            'div',
            { style: { display: 'flex', width: 'max-content', animation: 'ivwMarq 46s linear infinite' } },
            marquee
          )
        )
      );
    }

    renderOverlays(st, I) {
      var self = this;
      var selMetas = st.compare
        .map(function (id) {
          return I.find(function (m) {
            return m.id === id;
          });
        })
        .filter(Boolean);
      var cmpCols = ['var(--accent)', '#5d9c85', '#cf8a58'];

      var watchPanelItems = st.watch
        .map(function (id) {
          return I.find(function (m) {
            return m.id === id;
          });
        })
        .filter(Boolean);

      return [
        st.reqOpen
          ? h(
              'div',
              { key: 'req-bg', onClick: function () { self.setState({ reqOpen: false, reqSent: false }); }, style: { position: 'fixed', inset: 0, background: 'rgba(1,20,28,.45)', zIndex: 110 } }
            )
          : null,
        st.reqOpen
          ? h(
              'div',
              {
                key: 'req',
                style: {
                  position: 'fixed',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%,-50%)',
                  zIndex: 115,
                  width: 340,
                  background: 'var(--bg2)',
                  borderRadius: '24px 24px 24px 6px',
                  padding: 26,
                  boxShadow: '0 24px 60px rgba(1,20,28,.4)',
                },
              },
              !st.reqSent
                ? [
                    h('div', { key: 't', style: { fontFamily: 'Newsreader', fontWeight: 500, fontSize: 21, color: 'var(--text)' } }, 'Request an index'),
                    h('button', {
                      key: 'send',
                      style: ps("margin-top:14px;width:100%;height:40px;border:none;border-radius:999px;background:var(--accent);color:var(--on-accent);font:600 13px 'Archivo';cursor:pointer;"),
                      onClick: function () { self.setState({ reqSent: true }); },
                    }, 'Send request'),
                    h('button', {
                      key: 'cancel',
                      style: ps("margin-top:8px;width:100%;height:36px;border:1px solid var(--hairline);border-radius:999px;background:transparent;color:var(--text-dim);font:500 12.5px 'Archivo';cursor:pointer;"),
                      onClick: function () { self.setState({ reqOpen: false, reqSent: false }); },
                    }, 'Cancel'),
                  ]
                : [
                    h('div', { key: 'ok', style: { fontFamily: 'Newsreader', fontWeight: 500, fontSize: 21, color: 'var(--text)', marginTop: 12 } }, 'Request sent'),
                    h('button', {
                      key: 'done',
                      style: ps("margin-top:16px;width:100%;height:40px;border:none;border-radius:999px;background:var(--accent);color:var(--on-accent);font:600 13px 'Archivo';cursor:pointer;"),
                      onClick: function () { self.setState({ reqOpen: false, reqSent: false }); },
                    }, 'Done'),
                  ]
            )
          : null,
        h('div', {
          key: 'tip',
          ref: function (el) {
            self._tip = el;
          },
          style: {
            position: 'fixed',
            display: 'none',
            zIndex: 120,
            pointerEvents: 'none',
            background: '#013547',
            color: '#EBEBEB',
            font: "600 11px 'Archivo'",
            padding: '6px 12px',
            borderRadius: 999,
            whiteSpace: 'nowrap',
            boxShadow: '0 8px 20px rgba(1,20,28,.3)',
          },
        }, 'Open index →'),
        selMetas.length
          ? h(
              'div',
              {
                key: 'compare',
                style: {
                  position: 'fixed',
                  bottom: 22,
                  left: '50%',
                  transform: 'translateX(-50%)',
                  zIndex: 90,
                  width: 640,
                  maxWidth: 'calc(100vw - 360px)',
                  background: 'var(--bg2)',
                  borderRadius: '24px 24px 24px 6px',
                  boxShadow: '0 24px 60px var(--shadow)',
                  padding: '16px 20px 14px',
                },
              },
              h(
                'button',
                {
                  title: 'Clear and close',
                  style: ps(
                    'position:absolute;top:12px;right:12px;display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 12px;border-radius:999px;border:1px solid var(--hairline);background:var(--layer);color:var(--text);font:600 11px Archivo;cursor:pointer;'
                  ),
                  onClick: function () {
                    self.setState({ compare: [] });
                  },
                },
                'Clear ×'
              ),
              h(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10, paddingRight: 86 } },
                h('span', { style: ps("font:600 9px 'IBM Plex Mono';letter-spacing:.16em;text-transform:uppercase;color:var(--text-faint);") }, 'Compare · normalised · 90d'),
                selMetas.map(function (m, i) {
                  return h(
                    'button',
                    {
                      key: m.id,
                      style: ps(
                        "display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 11px;border-radius:999px;border:1px solid var(--hairline);background:transparent;color:var(--text-dim);font:500 11px 'Archivo';cursor:pointer;"
                      ),
                      onClick: function () {
                        self.toggleCompare(m.id);
                      },
                    },
                    h('span', { style: { width: 8, height: 8, borderRadius: '50%', background: cmpCols[i] } }),
                    m.name,
                    ' ×'
                  );
                })
              ),
              h('div', { style: { width: '100%' } }, Charts.compareChart(React, this.data, selMetas)),
              h(
                'div',
                {
                  style: {
                    fontSize: 10.5,
                    fontFamily: 'Archivo',
                    color: 'var(--text-faint)',
                    lineHeight: 1.5,
                    marginTop: 8,
                    borderTop: '1px solid var(--hairline)',
                    paddingTop: 8,
                  },
                },
                'Normalisation: each series is min–max scaled over the last 90 days — 0% = its lowest value in the period, 100% = its highest. Shapes are comparable; absolute levels are not.'
              )
            )
          : null,
        h(
          'div',
          {
            key: 'watchfloat',
            style: {
              position: 'fixed',
              bottom: 22,
              right: 22,
              zIndex: 100,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-end',
              gap: 10,
            },
          },
          st.watchOpen
            ? h(
                'div',
                {
                  style: {
                    width: 308,
                    background: 'var(--bg2)',
                    borderRadius: '24px 24px 4px 24px',
                    padding: 20,
                    boxShadow: '0 24px 60px var(--shadow)',
                  },
                },
                h(
                  'div',
                  { style: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 } },
                  h('div', { style: { fontFamily: 'Newsreader', fontWeight: 500, fontSize: 19, color: 'var(--text)' } }, 'Watchlist'),
                  h('span', { style: ps("font:500 10px 'IBM Plex Mono';letter-spacing:.14em;text-transform:uppercase;color:var(--text-faint);") }, 'saved locally')
                ),
                !st.watch.length
                  ? h('div', { style: { fontSize: 12, color: 'var(--text-faint)', marginTop: 8, fontFamily: 'Archivo', lineHeight: 1.6 } }, 'Nothing saved yet. Tap ☆ on any index to keep it here — no account needed.')
                  : [
                      h(
                        'div',
                        { key: 'wl', style: { display: 'flex', flexDirection: 'column', marginTop: 12, maxHeight: 280, overflowY: 'auto' } },
                        watchPanelItems.map(function (m) {
                          var s = m.series;
                          var ch = IVAN.fmtChange(m, s[s.length - 1], s[s.length - 2]);
                          return h(
                            'div',
                            {
                              key: m.id,
                              style: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderTop: '1px solid var(--hairline)', cursor: 'pointer' },
                              onClick: function () {
                                self.setState({ watchOpen: false });
                                self.openIndex(m.id);
                              },
                            },
                            h(
                              'div',
                              { style: { flex: 1, minWidth: 0 } },
                              h('div', { style: { fontSize: 12.5, fontFamily: 'Archivo', color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }, m.name),
                              h('div', { style: { display: 'flex', gap: 8, font: "500 11px 'IBM Plex Mono'", marginTop: 3 } },
                                h('span', { style: { color: 'var(--text-dim)' } }, IVAN.valStr(m, s[s.length - 1])),
                                h('span', { style: { color: ch.up ? 'var(--up)' : 'var(--down)' } }, ch.txt)
                              )
                            ),
                            h('button', {
                              title: 'Remove',
                              style: ps('width:24px;height:24px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid var(--hairline);background:transparent;color:var(--text-faint);font-size:12px;cursor:pointer;'),
                              onClick: function (e) { e.stopPropagation(); self.toggleWatch(m.id); },
                            }, '×')
                          );
                        })
                      ),
                      h('button', {
                        key: 'saved',
                        style: ps("margin-top:14px;width:100%;height:38px;border:none;border-radius:999px;background:var(--accent);color:var(--on-accent);font:600 12.5px 'Archivo';cursor:pointer;"),
                        onClick: function () { self.applyFilter('saved'); },
                      }, 'Show saved only'),
                      st.watch.length > 1
                        ? h('button', {
                            key: 'cs',
                            style: ps("margin-top:8px;width:100%;height:38px;border:1px solid var(--border-s);border-radius:999px;background:transparent;color:var(--text);font:500 12.5px 'Archivo';cursor:pointer;"),
                            onClick: function () { self.setState({ compare: st.watch.slice(0, 3), watchOpen: false }); },
                          }, 'Compare saved · ' + Math.min(3, st.watch.length))
                        : null,
                    ]
              )
            : null,
          h(
            'button',
            {
              'data-watchbtn': '1',
              title: 'Watchlist',
              style: ps(
                "height:44px;min-width:44px;padding:0 14px;display:inline-flex;align-items:center;justify-content:center;border-radius:999px;border:none;background:var(--accent);color:var(--on-accent);font:600 13px/1 'Archivo';cursor:pointer;box-shadow:0 12px 30px var(--shadow);"
              ),
              onClick: function () {
                self.setState({ watchOpen: !st.watchOpen });
              },
            },
            h('span', { style: { fontSize: 16, lineHeight: 1 } }, st.watch.length ? '★' : '☆'),
            h('span', { 'data-wlabel': '1' }, st.watch.length ? 'Watchlist · ' + st.watch.length : 'Watchlist')
          )
        ),
      ];
    }

    render() {
      var st = this.state;
      var I = this.data.indexes;
      var page = this.page();
      var list = this.filteredItems();
      var items = list.map(
        function (m, i) {
          return this.buildItem(m, i === 0, i);
        }.bind(this)
      );
      this._ids = items.map(function (x) {
        return x.id;
      });

      var contentStyle = ps(
        'flex:1;min-width:0;margin-left:' +
          (st.collapsed ? '64px' : '248px') +
          ';transition:margin-left .25s;' +
          (st.entering ? 'animation:ivwEnter .8s cubic-bezier(.16,1,.3,1) both;' : '')
      );

      var dmeta =
        page === 'detail'
          ? I.find(
              function (m) {
                return m.id === this.indexId();
              }.bind(this)
            )
          : null;

      var mainContent;
      if (page === 'home') {
        mainContent = this.renderHomeMain(st, items);
      } else if (!dmeta) {
        mainContent = this.renderNotFound();
      } else {
        mainContent = this.renderDetail(st, dmeta, this.detailData(dmeta));
      }

      return h(
        'div',
        { style: rootStyleObj(st.theme, st.accent) },
        this.renderSidebar(st, I, items),
        h('div', { style: contentStyle }, mainContent),
        st.welcomeOpen && page === 'home' ? this.renderWelcome(st, I) : null,
        this.renderOverlays(st, I)
      );
    }
  }

  /**
   * Экран загрузки на время запроса к /api/indexes.
   *
   * Тему берёт из тех же CSS-переменных, что и приложение, поэтому переход к
   * готовому интерфейсу не мигает фоном.
   */
  function BootSkeleton() {
    return h(
      'div',
      {
        style: mergeStyle(
          IVAN.rootStyleCss('light', '#DDBA9B'),
          'align-items:center;justify-content:center;flex-direction:column;gap:14px;'
        ),
      },
      h(
        'div',
        {
          style: {
            fontFamily: 'Newsreader',
            fontSize: 28,
            fontWeight: 500,
            letterSpacing: '-0.01em',
          },
        },
        'IVAN'
      ),
      h(
        'div',
        {
          style: {
            fontFamily: 'IBM Plex Mono',
            fontSize: 11,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--text-faint)',
          },
        },
        'Loading index data…'
      )
    );
  }

  /**
   * Экран ошибки, если /api/indexes недоступен.
   *
   * Сознательно не подставляем сгенерированные данные: показать выдуманные
   * значения индексов как настоящие хуже, чем честно сказать, что данных нет.
   */
  function BootError(props) {
    return h(
      'div',
      {
        style: mergeStyle(
          IVAN.rootStyleCss('light', '#DDBA9B'),
          'align-items:center;justify-content:center;flex-direction:column;gap:16px;padding:32px;text-align:center;'
        ),
      },
      h(
        'div',
        { style: { fontFamily: 'Newsreader', fontSize: 26, fontWeight: 500 } },
        'Index data unavailable'
      ),
      h(
        'div',
        {
          style: {
            fontFamily: 'Archivo',
            fontSize: 14,
            lineHeight: 1.6,
            color: 'var(--text-dim)',
            maxWidth: 420,
          },
        },
        'The terminal could not load index data from the server. Values are never simulated, so nothing is shown until the feed is back.'
      ),
      h(
        'button',
        {
          onClick: function () {
            window.location.reload();
          },
          style: {
            marginTop: 4,
            padding: '11px 20px',
            border: 'none',
            cursor: 'pointer',
            background: 'var(--accent)',
            color: 'var(--on-accent)',
            fontFamily: 'IBM Plex Mono',
            fontSize: 11.5,
            fontWeight: 500,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          },
        },
        'Retry'
      ),
      props && props.detail
        ? h(
            'div',
            {
              style: {
                fontFamily: 'IBM Plex Mono',
                fontSize: 10.5,
                color: 'var(--text-faint)',
                marginTop: 8,
              },
            },
            String(props.detail)
          )
        : null
    );
  }

  /**
   * Точка входа: читает dataset.body, грузит реальные данные и монтирует React 18.
   *
   * Данные тянутся до первого рендера, потому что IvanApp читает this.data уже в
   * конструкторе. Пока запрос в пути — скелетон, при отказе бэкенда — экран ошибки.
   */
  IVAN.boot = function () {
    var page = document.body.dataset.page || 'home';
    var indexId = document.body.dataset.indexId || null;
    var rootEl = document.getElementById('root');
    if (!rootEl) return;

    var root = ReactDOM.createRoot(rootEl);
    root.render(h(BootSkeleton));

    if (!IVAN.loadData) {
      root.render(h(BootError, { detail: 'data-api.js not loaded' }));
      return;
    }

    IVAN.loadData().then(
      function (data) {
        // Заголовок вкладки: на detail — имя индекса из полученных метаданных.
        if (page === 'detail' && indexId) {
          var meta = (data.indexes || []).find(function (m) {
            return m.id === indexId;
          });
          if (meta) document.title = meta.name + ' — IVAN';
        }
        root.render(h(IvanApp, { page: page, indexId: indexId, data: data }));
      },
      function (err) {
        console.error('IVAN: не удалось загрузить /api/indexes', err);
        root.render(h(BootError, { detail: err && err.message }));
      }
    );
  };

  global.IvanApp = IvanApp;
})(typeof window !== 'undefined' ? window : globalThis);
