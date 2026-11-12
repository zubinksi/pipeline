// Filters for the drug list. A filter icon beside "The drugs" opens a panel of
// chip groups (one per filter, so more can be added). Without JavaScript the
// icon stays hidden and every drug shows. The choice is kept in the URL.
(function () {
  var box = document.querySelector('[data-filter]');
  if (!box) return;
  var btn = box.querySelector('.ficon');
  var panel = box.querySelector('.fpanel');
  if (!btn || !panel) return;
  var count = btn.querySelector('.fcount');
  var chips = Array.prototype.slice.call(panel.querySelectorAll('.chip'));
  var groups = Array.prototype.slice.call(box.querySelectorAll('[data-group]'));
  var empty = box.querySelector('.f-empty');
  var want = {};
  chips.forEach(function (c) { want[c.dataset.k] = 'all'; });
  var params = new URLSearchParams(location.search);
  Object.keys(want).forEach(function (k) {
    var v = params.get(k);
    if (v && panel.querySelector('.chip[data-k="' + k + '"][data-v="' + v + '"]')) want[k] = v;
  });

  function apply() {
    chips.forEach(function (c) { c.setAttribute('aria-pressed', String(want[c.dataset.k] === c.dataset.v)); });
    var active = Object.keys(want).filter(function (k) { return want[k] !== 'all'; }).length;
    count.textContent = active; count.hidden = !active;
    btn.classList.toggle('on', active > 0);
    var total = 0;
    groups.forEach(function (g) {
      var shown = 0;
      g.querySelectorAll('.drug').forEach(function (r) {
        var ok = !r.dataset.untracked && Object.keys(want).every(function (k) {
          return want[k] === 'all' || (r.dataset[k] || '').split(' ').indexOf(want[k]) !== -1;
        });
        r.hidden = !ok;
        if (ok) shown++;
      });
      g.hidden = shown === 0;
      var gc = g.querySelector('[data-count]'); if (gc) gc.textContent = shown;
      total += shown;
    });
    box.querySelectorAll('[data-topic-sec]').forEach(function (s) {
      if (s.dataset.untracked) return;  // the panel hid it
      var n = s.querySelectorAll('.drug:not([hidden])').length;
      var c = s.querySelector('[data-tcount]'); if (c) c.textContent = n;
      s.hidden = n === 0;
    });
    empty.hidden = total > 0 || !box.querySelector('.drug:not([data-untracked])');
    var url = new URL(location.href);
    Object.keys(want).forEach(function (k) {
      if (want[k] === 'all') url.searchParams.delete(k); else url.searchParams.set(k, want[k]);
    });
    history.replaceState(history.state, '', url);
  }

  btn.addEventListener('click', function () {
    var open = panel.hidden;
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  });
  panel.addEventListener('click', function (e) {
    var c = e.target.closest('.chip');
    if (!c) return;
    want[c.dataset.k] = c.dataset.v;
    apply();
  });
  btn.hidden = false;
  apply();
})();
