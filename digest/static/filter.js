// Filters the drug list with the chips next to "The drugs". Without JavaScript
// the chips stay hidden and every drug shows. The choice is kept in the URL.
(function () {
  var box = document.querySelector('[data-filter]');
  if (!box) return;
  var bar = box.querySelector('.filters');
  if (!bar) return;
  var chips = Array.prototype.slice.call(bar.querySelectorAll('.chip'));
  var groups = Array.prototype.slice.call(box.querySelectorAll('[data-group]'));
  var empty = box.querySelector('.f-empty');
  var want = {};
  chips.forEach(function (c) { want[c.dataset.k] = 'all'; });
  var params = new URLSearchParams(location.search);
  Object.keys(want).forEach(function (k) {
    var v = params.get(k);
    if (v && bar.querySelector('.chip[data-k="' + k + '"][data-v="' + v + '"]')) want[k] = v;
  });

  function apply() {
    chips.forEach(function (c) { c.setAttribute('aria-pressed', String(want[c.dataset.k] === c.dataset.v)); });
    var total = 0;
    groups.forEach(function (g) {
      var shown = 0;
      g.querySelectorAll('.drug').forEach(function (r) {
        var ok = Object.keys(want).every(function (k) {
          return want[k] === 'all' || (r.dataset[k] || '').split(' ').indexOf(want[k]) !== -1;
        });
        r.hidden = !ok;
        if (ok) shown++;
      });
      g.hidden = shown === 0;
      g.querySelector('[data-count]').textContent = shown;
      total += shown;
    });
    empty.hidden = total > 0;
    var url = new URL(location.href);
    Object.keys(want).forEach(function (k) {
      if (want[k] === 'all') url.searchParams.delete(k); else url.searchParams.set(k, want[k]);
    });
    history.replaceState(history.state, '', url);
  }

  bar.addEventListener('click', function (e) {
    var c = e.target.closest('.chip');
    if (!c) return;
    want[c.dataset.k] = c.dataset.v;
    apply();
  });
  bar.hidden = false;
  apply();
})();
