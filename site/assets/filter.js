// Filters the pipeline by how a drug is taken and how often. Without
// JavaScript the filter bar stays hidden and every drug shows.
(function () {
  var box = document.querySelector('[data-filter]');
  if (!box) return;
  var bar = box.querySelector('.filters');
  var rows = Array.prototype.slice.call(box.querySelectorAll('.strip-row'));
  var count = box.querySelector('.f-count');
  var empty = box.querySelector('.f-empty');
  var state = { type: 'all', freq: 'all' };
  var params = new URLSearchParams(location.search);
  Object.keys(state).forEach(function (k) {
    var v = params.get(k);
    if (v && box.querySelector('[data-k="' + k + '"][data-v="' + v + '"]')) state[k] = v;
  });

  function apply() {
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (state.type === 'all' || r.dataset.type === state.type) &&
               (state.freq === 'all' || r.dataset.freq === state.freq);
      r.hidden = !ok;
      if (ok) shown++;
    });
    box.querySelectorAll('[data-k]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(state[b.dataset.k] === b.dataset.v));
    });
    count.textContent = shown === rows.length ? rows.length + ' drugs' : shown + ' of ' + rows.length + ' drugs';
    empty.hidden = shown > 0;
    var url = new URL(location.href);
    Object.keys(state).forEach(function (k) {
      if (state[k] === 'all') url.searchParams.delete(k); else url.searchParams.set(k, state[k]);
    });
    history.replaceState(null, '', url);
  }

  bar.addEventListener('click', function (e) {
    var b = e.target.closest('[data-k]');
    if (!b) return;
    state[b.dataset.k] = b.dataset.v;
    apply();
  });
  bar.hidden = false;
  apply();
})();
