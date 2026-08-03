/**
 * SVG-графики IVAN как React.createElement (spark, gauge, detail, compare).
 */
(function (global) {
  'use strict';

  var IV = global.IVAN;

  function spark(React, series, w, h) {
    var h_ = React.createElement;
    var s = series.slice(-32);
    var mn = Math.min.apply(null, s);
    var mx = Math.max.apply(null, s);
    var rg = mx - mn || 1;
    var dx = w / (s.length - 1);
    var yy = function (v) {
      return h - 3 - ((v - mn) / rg) * (h - 6);
    };
    var line = '';
    s.forEach(function (v, i) {
      line += (i ? 'L' : 'M') + (i * dx).toFixed(1) + ' ' + yy(v).toFixed(1) + ' ';
    });
    var area =
      'M0 ' +
      h +
      ' ' +
      s
        .map(function (v, i) {
          return 'L' + (i * dx).toFixed(1) + ' ' + yy(v).toFixed(1);
        })
        .join(' ') +
      ' L' +
      w +
      ' ' +
      h +
      ' Z';
    var up = s[s.length - 1] >= s[0];
    var col = up ? 'var(--up)' : 'var(--down)';
    var gid = 'sg' + Math.random().toString(36).slice(2, 8);
    return h_(
      'svg',
      {
        viewBox: '0 0 ' + w + ' ' + h,
        width: w,
        height: h,
        style: { display: 'block', overflow: 'visible' },
      },
      h_(
        'defs',
        null,
        h_(
          'linearGradient',
          { id: gid, x1: 0, y1: 0, x2: 0, y2: 1 },
          h_('stop', { offset: '0%', stopColor: col, stopOpacity: 0.26 }),
          h_('stop', { offset: '100%', stopColor: col, stopOpacity: 0 })
        )
      ),
      h_('path', { d: area, style: { fill: 'url(#' + gid + ')', stroke: 'none' } }),
      h_('path', {
        d: line,
        style: {
          fill: 'none',
          stroke: col,
          strokeWidth: 1.6,
          strokeLinejoin: 'round',
          strokeLinecap: 'round',
        },
      }),
      h_('circle', { cx: w, cy: yy(s[s.length - 1]), r: 2.3, style: { fill: col } })
    );
  }

  function gauge(React, meta, val) {
    var h_ = React.createElement;
    var W = 300;
    var H = 190;
    var cx = 150;
    var cy = 158;
    var r = 120;
    var sw = 22;
    var pt = function (f) {
      var a = Math.PI * (1 - f);
      return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
    };
    var arc = function (f0, f1) {
      var p0 = pt(f0);
      var p1 = pt(f1);
      return (
        'M' +
        p0.x.toFixed(1) +
        ' ' +
        p0.y.toFixed(1) +
        ' A ' +
        r +
        ' ' +
        r +
        ' 0 0 1 ' +
        p1.x.toFixed(1) +
        ' ' +
        p1.y.toFixed(1)
      );
    };
    var segs = [
      [0, 0.25, '#c05b3d'],
      [0.25, 0.48, '#cf8a58'],
      [0.48, 0.53, '#b3a26b'],
      [0.53, 0.75, '#5d9c85'],
      [0.75, 1, '#2f8268'],
    ];
    var frac = Math.max(0, Math.min(1, (val - meta.min) / (meta.max - meta.min)));
    var np = pt(frac);
    var kids = [];
    segs.forEach(function (sg, i) {
      kids.push(
        h_('path', {
          key: 's' + i,
          d: arc(sg[0], sg[1]),
          style: { fill: 'none', stroke: sg[2], strokeWidth: sw, strokeLinecap: 'butt' },
        })
      );
    });
    kids.push(
      h_('line', {
        key: 'nd',
        x1: cx,
        y1: cy,
        x2: np.x,
        y2: np.y,
        style: { stroke: 'var(--band-text)', strokeWidth: 3, strokeLinecap: 'round' },
      })
    );
    kids.push(
      h_('circle', {
        key: 'hub',
        cx: cx,
        cy: cy,
        r: 8,
        style: { fill: 'var(--band)', stroke: 'var(--band-line)', strokeWidth: 2 },
      })
    );
    kids.push(
      h_(
        'text',
        {
          key: 'v',
          x: cx,
          y: cy - 34,
          style: {
            fontFamily: "'IBM Plex Mono'",
            fontWeight: 600,
            fontSize: 42,
            fill: 'var(--band-text)',
            textAnchor: 'middle',
          },
        },
        Math.round(val)
      )
    );
    kids.push(
      h_(
        'text',
        {
          key: 'mn',
          x: pt(0).x,
          y: cy + 18,
          style: {
            fontFamily: "'IBM Plex Mono'",
            fontSize: 11,
            fill: 'var(--band-dim)',
            textAnchor: 'middle',
          },
        },
        meta.min
      )
    );
    kids.push(
      h_(
        'text',
        {
          key: 'mx',
          x: pt(1).x,
          y: cy + 18,
          style: {
            fontFamily: "'IBM Plex Mono'",
            fontSize: 11,
            fill: 'var(--band-dim)',
            textAnchor: 'middle',
          },
        },
        meta.max
      )
    );
    return h_('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', style: { display: 'block' } }, kids);
  }

  /**
   * Основной график детальной страницы: ряд индекса, объём, опциональное сравнение, alert-линия.
   */
  function detailChart(React, opts) {
    var h_ = React.createElement;
    var meta = opts.meta;
    var data = opts.data;
    var range = opts.range;
    var hover = opts.hover;
    var setHover = opts.setHover;
    var cmpWith = opts.cmpWith;
    var alerts = opts.alerts || {};

    var N = data.dates.length;
    var spanMap = { '30d': 30, '90d': 90, '180d': 180, '1y': 365 };
    var span = spanMap[range] || 90;
    var a = Math.max(0, N - span);
    var S = meta.series.slice(a);
    // Объём есть только у индексов, привязанных к торгуемому рынку (см.
    // indices/volumes.py). Если его нет — столбики не рисуем, а высвободившуюся
    // полосу отдаём линии индекса.
    var V = meta.volume ? meta.volume.slice(a) : null;
    var DT = data.dates.slice(a);
    var L = S.length;
    var cw = cmpWith || 'btc';
    var P = null;
    var cFmt = null;
    var cShort = '';

    if (cw === 'btc') {
      P = data.btc.slice(a);
      cShort = 'BTC';
      cFmt = function (v) {
        return '$' + IV.kfmt(v);
      };
    } else if (cw !== 'none') {
      var cm = data.indexes.find(function (x) {
        return x.id === cw && x.id !== meta.id;
      });
      if (cm) {
        P = cm.series.slice(a);
        cShort = cm.name.length > 16 ? cm.name.slice(0, 15) + '…' : cm.name;
        cFmt = function (v) {
          return IV.fmt(v, cm.dec) + (cm.unit || '');
        };
      }
    }

    var W = 1000;
    var H = 380;
    var padL = 58;
    var padR = 68;
    var padT = 16;
    var padB = 40;
    var iw = W - padL - padR;
    var fullH = H - padT - padB;
    var volH = V ? 56 : 0;
    var gap = V ? 16 : 0;
    var lineH = fullH - volH - gap;
    var top = padT;
    var bot = padT + lineH;
    var iMin = Math.min.apply(null, S);
    var iMax = Math.max.apply(null, S);
    var ip = (iMax - iMin) * 0.14 || 1;
    var lo = iMin - ip;
    var hi = iMax + ip;
    var bMin = P ? Math.min.apply(null, P) : 0;
    var bMax = P ? Math.max.apply(null, P) : 1;
    var bp = (bMax - bMin) * 0.14 || 1;
    var blo = bMin - bp;
    var bhi = bMax + bp;
    var vMax = V ? Math.max.apply(null, V) || 1 : 1;
    var X = function (i) {
      return padL + (iw * i) / (L - 1);
    };
    var Yi = function (v) {
      return bot - ((v - lo) / (hi - lo)) * lineH;
    };
    var Yb = function (v) {
      return bot - ((v - blo) / (bhi - blo)) * lineH;
    };
    var kids = [];
    var ticks = 5;

    for (var k = 0; k < ticks; k++) {
      var f = k / (ticks - 1);
      var yy = top + lineH * f;
      var val = hi - (hi - lo) * f;
      var bval = bhi - (bhi - blo) * f;
      kids.push(
        h_('line', {
          key: 'g' + k,
          x1: padL,
          y1: yy,
          x2: padL + iw,
          y2: yy,
          style: { stroke: 'var(--grid)', strokeWidth: 1 },
        })
      );
      kids.push(
        h_(
          'text',
          {
            key: 'gl' + k,
            x: padL - 9,
            y: yy + 3.5,
            style: {
              fontFamily: "'IBM Plex Mono'",
              fontSize: 10.5,
              fill: 'var(--text-faint)',
              textAnchor: 'end',
            },
          },
          IV.fmt(val, meta.dec)
        )
      );
      if (P) {
        kids.push(
          h_(
            'text',
            {
              key: 'gr' + k,
              x: padL + iw + 9,
              y: yy + 3.5,
              style: {
                fontFamily: "'IBM Plex Mono'",
                fontSize: 10.5,
                fill: 'var(--text-faint)',
                textAnchor: 'start',
              },
            },
            cFmt(bval)
          )
        );
      }
    }

    if (V) {
      var bw = Math.max(1, (iw / L) * 0.62);
      V.forEach(function (vv, i) {
        var hgt = (vv / vMax) * volH;
        kids.push(
          h_('rect', {
            key: 'v' + i,
            x: X(i) - bw / 2,
            y: padT + fullH - hgt,
            width: bw,
            height: hgt,
            rx: 0.5,
            style: { fill: 'var(--accent)', opacity: 0.18 },
          })
        );
      });
    }

    var line = '';
    S.forEach(function (v, i) {
      var x = X(i);
      var y = Yi(v);
      line += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
    });
    var area =
      'M' +
      X(0).toFixed(1) +
      ' ' +
      bot +
      ' ' +
      S.map(function (v, i) {
        return 'L' + X(i).toFixed(1) + ' ' + Yi(v).toFixed(1);
      }).join(' ') +
      ' L' +
      X(L - 1).toFixed(1) +
      ' ' +
      bot +
      ' Z';
    var gid = 'cg' + Math.random().toString(36).slice(2, 8);
    kids.push(
      h_(
        'defs',
        { key: 'df' },
        h_(
          'linearGradient',
          { id: gid, x1: 0, y1: 0, x2: 0, y2: 1 },
          h_('stop', { offset: '0%', stopColor: 'var(--accent)', stopOpacity: 0.22 }),
          h_('stop', { offset: '100%', stopColor: 'var(--accent)', stopOpacity: 0 })
        )
      )
    );
    kids.push(h_('path', { key: 'ar', d: area, style: { fill: 'url(#' + gid + ')', stroke: 'none' } }));

    if (P) {
      var bl = '';
      P.forEach(function (v, i) {
        var x = X(i);
        var y = Yb(v);
        bl += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
      });
      kids.push(
        h_('path', {
          key: 'bl',
          d: bl,
          style: {
            fill: 'none',
            stroke: 'var(--text-faint)',
            strokeWidth: 1.4,
            strokeDasharray: '4 4',
            opacity: 0.85,
          },
        })
      );
    }

    kids.push(
      h_('path', {
        key: 'ln',
        d: line,
        style: {
          fill: 'none',
          stroke: 'var(--accent)',
          strokeWidth: 2,
          strokeLinejoin: 'round',
          strokeLinecap: 'round',
        },
      })
    );

    var al = alerts[meta.id];
    if (al && isFinite(al.value) && al.value >= lo && al.value <= hi) {
      var ty = Yi(al.value);
      var trig = IV.alertTriggered(meta, al);
      var col = trig ? 'var(--down)' : 'var(--text-dim)';
      kids.push(
        h_('line', {
          key: 'alr',
          x1: padL,
          y1: ty,
          x2: padL + iw,
          y2: ty,
          style: { stroke: col, strokeWidth: 1.5, strokeDasharray: '6 4' },
        })
      );
      kids.push(
        h_('rect', {
          key: 'alb',
          x: padL + 5,
          y: ty - 20,
          width: 150,
          height: 17,
          rx: 8.5,
          style: { fill: col },
        })
      );
      kids.push(
        h_(
          'text',
          {
            key: 'alt',
            x: padL + 14,
            y: ty - 8,
            style: {
              fontFamily: "'IBM Plex Mono'",
              fontSize: 9.5,
              letterSpacing: '.1em',
              fill: 'var(--bg2)',
            },
          },
          'ALERT ' +
            (al.op === 'below' ? '<' : '>') +
            ' ' +
            IV.fmt(al.value, meta.dec) +
            (trig ? ' · TRIGGERED' : '')
        )
      );
    }

    var steps = 6;
    for (var kx = 0; kx <= steps; kx++) {
      var idx = Math.round(((L - 1) * kx) / steps);
      kids.push(
        h_(
          'text',
          {
            key: 'x' + kx,
            x: X(idx),
            y: H - 14,
            style: {
              fontFamily: "'IBM Plex Mono'",
              fontSize: 10.5,
              fill: 'var(--text-faint)',
              textAnchor: kx === 0 ? 'start' : kx === steps ? 'end' : 'middle',
            },
          },
          IV.fmtD(DT[idx])
        )
      );
    }

    if (hover != null && hover >= 0 && hover < L) {
      var x = X(hover);
      var iv = S[hover];
      var bv = P ? P[hover] : null;
      var vv = V ? V[hover] : null;
      kids.push(
        h_('line', {
          key: 'cx',
          x1: x,
          y1: top,
          x2: x,
          y2: padT + fullH,
          style: { stroke: 'var(--border-s)', strokeWidth: 1, strokeDasharray: '3 3' },
        })
      );
      kids.push(
        h_('circle', {
          key: 'di',
          cx: x,
          cy: Yi(iv),
          r: 3.5,
          style: { fill: 'var(--accent)', stroke: 'var(--bg2)', strokeWidth: 2 },
        })
      );
      if (P) {
        kids.push(
          h_('circle', {
            key: 'db',
            cx: x,
            cy: Yb(bv),
            r: 3,
            style: { fill: 'var(--text-faint)', stroke: 'var(--bg2)', strokeWidth: 1.5 },
          })
        );
      }
      var bwid = 176;
      var bx = x > W * 0.62 ? x - bwid - 12 : x + 12;
      var by = top + 6;
      // Дата + значение индекса — базовые 48px, плюс по строке на сравнение и
      // на объём, если они есть. Иначе под отсутствующим объёмом остаётся пустота.
      var bhgt = 48 + (P ? 18 : 0) + (vv != null ? 18 : 0);
      kids.push(
        h_('rect', {
          key: 'tb',
          x: bx,
          y: by,
          width: bwid,
          height: bhgt,
          rx: 12,
          style: { fill: 'var(--bg)', stroke: 'var(--border-s)', strokeWidth: 1 },
        })
      );
      kids.push(
        h_(
          'text',
          {
            key: 't0',
            x: bx + 12,
            y: by + 19,
            style: { fontFamily: "'Archivo'", fontSize: 11, fontWeight: 600, fill: 'var(--text)' },
          },
          IV.fmtDLong(DT[hover])
        )
      );
      kids.push(
        h_('rect', {
          key: 'sw1',
          x: bx + 12,
          y: by + 30,
          width: 9,
          height: 9,
          rx: 2,
          style: { fill: 'var(--accent)' },
        })
      );
      kids.push(
        h_(
          'text',
          {
            key: 't1',
            x: bx + 27,
            y: by + 38,
            style: { fontFamily: "'IBM Plex Mono'", fontSize: 11, fill: 'var(--text-dim)' },
          },
          IV.fmt(iv, meta.dec) + meta.unit
        )
      );
      if (P) {
        kids.push(
          h_('rect', {
            key: 'sw2',
            x: bx + 12,
            y: by + 47,
            width: 9,
            height: 9,
            rx: 2,
            style: { fill: 'var(--text-faint)' },
          })
        );
        kids.push(
          h_(
            'text',
            {
              key: 't2',
              x: bx + 27,
              y: by + 55,
              style: { fontFamily: "'IBM Plex Mono'", fontSize: 10.5, fill: 'var(--text-dim)' },
            },
            cShort + ' ' + cFmt(bv)
          )
        );
      }
      if (vv != null) {
        kids.push(
          h_(
            'text',
            {
              key: 't3',
              x: bx + 12,
              y: by + (P ? 72 : 54),
              style: { fontFamily: "'IBM Plex Mono'", fontSize: 11, fill: 'var(--text-faint)' },
            },
            // Подпись из метаданных: у ставки финансирования это оборот
            // бессрочного контракта, а не спота.
            (meta.volumeLabel || 'Volume') + ' $' + IV.kfmt(vv)
          )
        );
      }
    }

    kids.push(
      h_('rect', {
        key: 'ov',
        x: padL,
        y: padT,
        width: iw,
        height: fullH,
        style: { fill: 'transparent', cursor: 'crosshair' },
        onMouseMove: function (e) {
          var svg = e.currentTarget.ownerSVGElement;
          var rc = svg.getBoundingClientRect();
          var rx = ((e.clientX - rc.left) / rc.width) * W;
          var i = Math.round(((rx - padL) / iw) * (L - 1));
          i = Math.max(0, Math.min(L - 1, i));
          if (i !== hover) setHover(i);
        },
        onMouseLeave: function () {
          if (hover != null) setHover(null);
        },
      })
    );

    return h_('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', style: { display: 'block' } }, kids);
  }

  /** Нормализованный overlay для compare tray (90d) */
  function compareChart(React, data, sel) {
    var h_ = React.createElement;
    var W = 600;
    var H = 196;
    var padL = 46;
    var padR = 10;
    var padT = 12;
    var padB = 34;
    var iw = W - padL - padR;
    var ih = H - padT - padB;
    var cols = ['var(--accent)', '#5d9c85', '#cf8a58'];
    var kids = [];

    [1, 0.5, 0].forEach(function (f, i) {
      var yy = padT + ih * (1 - f);
      kids.push(
        h_('line', {
          key: 'g' + i,
          x1: padL,
          y1: yy,
          x2: padL + iw,
          y2: yy,
          style: { stroke: 'var(--grid)', strokeWidth: 1 },
        })
      );
      kids.push(
        h_(
          'text',
          {
            key: 'gy' + i,
            x: padL - 8,
            y: yy + 3.5,
            style: {
              fontFamily: "'IBM Plex Mono'",
              fontSize: 10,
              fill: 'var(--text-faint)',
              textAnchor: 'end',
            },
          },
          Math.round(f * 100) + '%'
        )
      );
    });

    kids.push(
      h_(
        'text',
        {
          key: 'yt',
          x: 12,
          y: padT + ih / 2,
          transform: 'rotate(-90 12 ' + (padT + ih / 2) + ')',
          style: {
            fontFamily: "'IBM Plex Mono'",
            fontSize: 9,
            letterSpacing: '.12em',
            fill: 'var(--text-faint)',
            textAnchor: 'middle',
          },
        },
        '% OF 90D RANGE'
      )
    );

    var DT = data.dates.slice(-90);
    [0, 0.25, 0.5, 0.75, 1].forEach(function (f, i) {
      var idx = Math.round((DT.length - 1) * f);
      kids.push(
        h_(
          'text',
          {
            key: 'gx' + i,
            x: padL + iw * f,
            y: H - 20,
            style: {
              fontFamily: "'IBM Plex Mono'",
              fontSize: 10,
              fill: 'var(--text-faint)',
              textAnchor: f === 0 ? 'start' : f === 1 ? 'end' : 'middle',
            },
          },
          IV.fmtD(DT[idx])
        )
      );
    });

    kids.push(
      h_(
        'text',
        {
          key: 'xt',
          x: padL + iw / 2,
          y: H - 5,
          style: {
            fontFamily: "'IBM Plex Mono'",
            fontSize: 9,
            letterSpacing: '.12em',
            fill: 'var(--text-faint)',
            textAnchor: 'middle',
          },
        },
        'DATE · LAST 90 DAYS'
      )
    );

    sel.forEach(function (m, si) {
      var s = m.series.slice(-90);
      var mn = Math.min.apply(null, s);
      var mx = Math.max.apply(null, s);
      var rg = mx - mn || 1;
      var d = '';
      s.forEach(function (v, i) {
        var x = padL + (iw * i) / (s.length - 1);
        var y = padT + ih - ((v - mn) / rg) * ih;
        d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
      });
      kids.push(
        h_('path', {
          key: 'l' + si,
          d: d,
          style: {
            fill: 'none',
            stroke: cols[si],
            strokeWidth: 2,
            strokeLinejoin: 'round',
            strokeLinecap: 'round',
          },
        })
      );
    });

    return h_('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', style: { display: 'block' } }, kids);
  }

  global.IVANCharts = {
    spark: spark,
    gauge: gauge,
    detailChart: detailChart,
    compareChart: compareChart,
  };
})(typeof window !== 'undefined' ? window : globalThis);
