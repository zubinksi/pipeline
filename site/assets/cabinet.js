// The cabinet: which drugs you follow. Saved in this browser; with nothing saved,
// every drug is followed. On the cabinet page the checkboxes edit the choice; on
// other pages, rows for drugs you don't follow are hidden (data-untracked tells
// filter.js to leave them hidden).
(function () {
  var KEY = 'cabinet';
  function load() {
    try { var v = JSON.parse(localStorage.getItem(KEY)); return Array.isArray(v) ? v : null; } catch (e) { return null; }
  }
  function save(ids) { try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch (e) {} }
  var mine = load();

  var form = document.querySelector('[data-cabinet]');
  if (form) {
    var boxes = Array.prototype.slice.call(form.querySelectorAll('input[name="drug"]'));
    boxes.forEach(function (b) { b.checked = !mine || mine.indexOf(b.value) !== -1; });
    // each group has one button: "Select all" until every box is ticked, then "Clear"
    var groups = Array.prototype.slice.call(form.querySelectorAll('fieldset'));
    function sync() {
      groups.forEach(function (g) {
        var bs = g.querySelectorAll('input[name="drug"]');
        var all = Array.prototype.every.call(bs, function (b) { return b.checked; });
        var btn = g.querySelector('[data-all]');
        btn.textContent = all ? 'Clear' : 'Select all';
        btn.dataset.all = all ? 'on' : 'off';
      });
    }
    function store() {
      save(boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }));
      sync();
    }
    groups.forEach(function (g) {
      var btn = g.querySelector('[data-all]');
      btn.hidden = false;
      btn.addEventListener('click', function () {
        var on = btn.dataset.all !== 'on';
        g.querySelectorAll('input[name="drug"]').forEach(function (b) { b.checked = on; });
        store();
      });
    });
    form.addEventListener('change', store);
    sync();
    return;
  }
  if (!mine) return;

  document.querySelectorAll('[data-drug]').forEach(function (el) {
    if (mine.indexOf(el.dataset.drug) === -1) { el.hidden = true; el.dataset.untracked = '1'; }
  });
  // tidy up: group counts, empty groups and sections, the total
  document.querySelectorAll('[data-group]').forEach(function (g) {
    var shown = g.querySelectorAll('.drug:not([data-untracked])').length;
    g.querySelector('[data-count]').textContent = shown;
    g.hidden = shown === 0;
  });
  document.querySelectorAll('.dtable').forEach(function (t) {
    var shown = t.querySelectorAll('.drug:not([data-untracked])').length;
    var sec = t.closest('.section');
    var total = sec.querySelector('[data-total]');
    if (total) total.textContent = shown;
    var empty = sec.querySelector('.cab-empty');
    if (empty) empty.hidden = shown > 0;
    if (!shown) { t.hidden = true; var f = sec.querySelector('.ficon'); if (f) f.remove(); }
  });
  document.querySelectorAll('.tl-list').forEach(function (l) {
    if (!l.querySelector('.tl:not([hidden])')) l.closest('.section').hidden = true;
  });
})();
