// Your labs: results kept only in this browser (localStorage), drawn as one small
// chart per marker with the common reference band. Nothing is sent anywhere.
(function () {
  var root = document.querySelector('[data-labs]');
  if (!root) return;
  var KEY = 'readout-labs';
  var MARKERS = [
    { k: 'ldl', name: 'LDL', unit: 'mg/dL', band: [0, 100], bandLabel: 'below 100' },
    { k: 'apob', name: 'ApoB', unit: 'mg/dL' },
    { k: 'hdl', name: 'HDL', unit: 'mg/dL', band: [40, null], bandLabel: '40 or above' },
    { k: 'tg', name: 'Triglycerides', unit: 'mg/dL', band: [0, 150], bandLabel: 'below 150' },
    { k: 'lpa', name: 'Lp(a)', unit: 'nmol/L', band: [0, 75], bandLabel: 'below 75' },
    { k: 'crp', name: 'hs-CRP', unit: 'mg/L', band: [0, 1], bandLabel: 'below 1' }
  ];
  function load() {
    try { var v = JSON.parse(localStorage.getItem(KEY)); return Array.isArray(v) ? v : []; } catch (e) { return []; }
  }
  function save(list) { try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {} }
  var data = load();
  var NS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var a in attrs) e.setAttribute(a, attrs[a]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function fmt(v) { return (Math.round(v * 10) / 10).toString(); }
  function niceDate(iso) {
    var d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
  }
  function status(m, v) {
    if (!m.band) return '';
    var lo = m.band[0], hi = m.band[1];
    if (hi != null && v >= hi) return 'Above range';
    if (lo != null && v < lo) return 'Below range';
    return 'In range';
  }

  function chart(m, pts, width) {
    var W = Math.max(280, Math.round(width || 560)), H = 112, L = 8, R = 48, T = 14, B = 22;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, class: 'lchart', role: 'img',
                          'aria-label': m.name + ' over time' });
    var vals = pts.map(function (p) { return p.v; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var edge = m.band ? (m.band[1] != null ? m.band[1] : m.band[0]) : null;
    if (edge != null) { lo = Math.min(lo, edge); hi = Math.max(hi, edge); }  // the band's edge is always in view
    var pad = (hi - lo) * 0.18 || Math.max(1, hi * 0.2);
    lo = Math.max(0, lo - pad); hi = hi + pad;
    var t0 = new Date(pts[0].d).getTime(), t1 = new Date(pts[pts.length - 1].d).getTime();
    var x = function (d) { return pts.length === 1 ? L + (W - L - R) / 2 : L + (new Date(d).getTime() - t0) / (t1 - t0) * (W - L - R); };
    var y = function (v) { return T + (1 - (v - lo) / (hi - lo)) * (H - T - B); };
    // the reference band
    if (m.band) {
      var bTop = m.band[1] == null ? hi : Math.min(m.band[1], hi), bBot = Math.max(m.band[0] || lo, lo);
      el('rect', { x: L, y: y(bTop), width: W - L - R, height: Math.max(0, y(bBot) - y(bTop)), class: 'lband' }, svg);
      el('line', { x1: L, x2: W - R, y1: y(edge), y2: y(edge), class: 'ledge' }, svg);
      // the band's edge, labelled at the left, just inside the band
      var inside = m.band[1] != null ? 12 : -5;
      var tl = el('text', { x: L + 4, y: y(edge) + inside, class: 'ltick ledge-l' }, svg); tl.textContent = edge;
    }
    el('line', { x1: L, x2: W - R, y1: H - B, y2: H - B, class: 'laxis' }, svg);
    var d0 = el('text', { x: L, y: H - 6, class: 'ltick' }, svg); d0.textContent = niceDate(pts[0].d);
    if (pts.length > 1) {
      var d1 = el('text', { x: W - R, y: H - 6, class: 'ltick', 'text-anchor': 'end' }, svg); d1.textContent = niceDate(pts[pts.length - 1].d);
      el('polyline', { points: pts.map(function (p) { return x(p.d) + ',' + y(p.v); }).join(' '), class: 'lline' }, svg);
    }
    pts.forEach(function (p, i) {
      var g = el('g', { class: 'lpt' + (i === pts.length - 1 ? ' last' : '') }, svg);
      el('circle', { cx: x(p.d), cy: y(p.v), r: 9, class: 'lhit' }, g);  // a bigger target than the mark
      el('circle', { cx: x(p.d), cy: y(p.v), r: i === pts.length - 1 ? 4.5 : 3.5, class: 'ldot' }, g);
      var tt = el('title', {}, g); tt.textContent = niceDate(p.d) + ': ' + fmt(p.v) + ' ' + m.unit;
    });
    var last = pts[pts.length - 1];
    var lab = el('text', { x: x(last.d) + 8, y: y(last.v) + 4, class: 'lval' }, svg);
    lab.textContent = fmt(last.v);
    if (x(last.d) + 8 + 40 > W) { lab.setAttribute('x', x(last.d) - 8); lab.setAttribute('text-anchor', 'end'); lab.setAttribute('y', y(last.v) - 9); }
    return svg;
  }

  function render() {
    data.sort(function (a, b) { return a.date < b.date ? -1 : 1; });
    var box = root.querySelector('[data-markers]');
    box.innerHTML = '';
    root.querySelector('.labs-empty').hidden = data.length > 0;
    MARKERS.forEach(function (m) {
      var pts = data.filter(function (r) { return r[m.k] != null && r[m.k] !== ''; })
                    .map(function (r) { return { d: r.date, v: +r[m.k] }; });
      if (!pts.length) return;
      var last = pts[pts.length - 1], prev = pts[pts.length - 2];
      var row = document.createElement('div'); row.className = 'marker';
      var st = status(m, last.v);
      var change = prev ? (last.v - prev.v) : null;
      row.innerHTML =
        '<div class="mk-head"><span class="mk-name">' + m.name + '</span>' +
        '<span class="mk-val">' + fmt(last.v) + ' <em>' + m.unit + '</em></span>' +
        (st ? '<span class="mk-st ' + (st === 'In range' ? 'ok' : 'out') + '">' + st + '</span>' : '') +
        (change != null ? '<span class="mk-chg">' + (change > 0 ? '▲ ' : change < 0 ? '▼ ' : '') + fmt(Math.abs(change)) + ' since ' + niceDate(prev.d) + '</span>' : '') +
        '</div>' +
        (m.band ? '<div class="mk-band">Reference: ' + m.bandLabel + '</div>' : '');
      row.appendChild(chart(m, pts, box.clientWidth));
      box.appendChild(row);
    });
    var tbl = document.querySelector('[data-labs-table]'), body = document.querySelector('[data-labs-rows]');
    tbl.hidden = !data.length;
    body.innerHTML = '';
    data.slice().reverse().forEach(function (r) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td class="nowrap">' + r.date + '</td>' + MARKERS.map(function (m) {
        return '<td>' + (r[m.k] != null && r[m.k] !== '' ? fmt(+r[m.k]) : '–') + '</td>';
      }).join('') + '<td><button type="button" class="labs-del" aria-label="Delete ' + r.date + '">Delete</button></td>';
      tr.querySelector('.labs-del').addEventListener('click', function () {
        if (!confirm('Delete the results from ' + r.date + '?')) return;
        data = data.filter(function (x) { return x !== r; }); save(data); render();
      });
      body.appendChild(tr);
    });
  }

  var form = document.querySelector('[data-labs-form]');
  form.date.value = new Date().toISOString().slice(0, 10);
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var rec = { date: form.date.value };
    var any = false;
    MARKERS.forEach(function (m) {
      var v = form[m.k].value;
      if (v !== '') { rec[m.k] = +v; any = true; }
    });
    if (!any) { alert('Enter at least one result.'); return; }
    data = data.filter(function (x) { return x.date !== rec.date; }).concat([rec]);  // one set per date
    save(data); render();
    MARKERS.forEach(function (m) { form[m.k].value = ''; });
  });
  document.querySelector('[data-labs-export]').addEventListener('click', function () {
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'readout-labs.json'; a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });
  document.querySelector('[data-labs-import]').addEventListener('change', function (e) {
    var f = e.target.files[0]; if (!f) return;
    f.text().then(function (t) {
      var list = JSON.parse(t);
      if (!Array.isArray(list)) throw new Error('not a list');
      var byDate = {};
      data.concat(list).forEach(function (r) { if (r && /^\d{4}-\d{2}-\d{2}$/.test(r.date)) byDate[r.date] = r; });
      data = Object.keys(byDate).map(function (k) { return byDate[k]; });
      save(data); render();
    }).catch(function () { alert("That file couldn't be read."); });
  });
  render();
  var rw = box0().clientWidth;
  window.addEventListener('resize', function () {
    var w = box0().clientWidth; if (Math.abs(w - rw) > 20) { rw = w; render(); }
  });
  function box0() { return root.querySelector('[data-markers]'); }
})();
