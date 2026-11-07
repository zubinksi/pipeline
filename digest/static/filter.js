// Filters the drug list by how it's taken and how often. Without JavaScript
// the dropdowns stay hidden and every drug shows.
(function () {
  var box = document.querySelector('[data-filter]');
  if (!box) return;
  var bar = box.querySelector('.filters');
  if (!bar) return;
  var selects = Array.prototype.slice.call(bar.querySelectorAll('select'));
  var groups = Array.prototype.slice.call(box.querySelectorAll('[data-group]'));
  var empty = box.querySelector('.f-empty');
  var attr = { lowers: 'lowers', freq: 'freq' };
  var params = new URLSearchParams(location.search);
  selects.forEach(function (s) {
    var v = params.get(s.dataset.k);
    if (v && s.querySelector('option[value="' + v + '"]')) s.value = v;
  });

  function apply() {
    var want = {};
    selects.forEach(function (s) {
      want[s.dataset.k] = s.value;
      s.classList.toggle('is-on', s.value !== 'all');
    });
    var total = 0;
    groups.forEach(function (g) {
      var shown = 0;
      g.querySelectorAll('.drug').forEach(function (r) {
        var ok = Object.keys(want).every(function (k) {
          return want[k] === 'all' || (r.dataset[attr[k]] || '').split(' ').indexOf(want[k]) !== -1;
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
    history.replaceState(null, '', url);
  }

  selects.forEach(function (s) { s.addEventListener('change', apply); });
  bar.hidden = false;
  apply();
})();
