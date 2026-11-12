// Coming up: switch between the list and the six-month calendar. The choice is
// remembered in this browser. Without JavaScript the list shows and the toggle stays hidden.
(function () {
  var sec = document.querySelector('[data-cal-sec]');
  if (!sec) return;
  var toggle = sec.querySelector('[data-cal-toggle]');
  if (!toggle) return;
  var KEY = 'readout-cal-view';
  function show(view) {
    sec.querySelectorAll('[data-cal-view]').forEach(function (v) { v.hidden = v.dataset.calView !== view; });
    toggle.querySelectorAll('[data-view]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.view === view)); });
    try { localStorage.setItem(KEY, view); } catch (e) {}
  }
  toggle.addEventListener('click', function (e) {
    var b = e.target.closest('[data-view]'); if (b) show(b.dataset.view);
  });
  var saved = 'list';
  try { saved = localStorage.getItem(KEY) || 'list'; } catch (e) {}
  toggle.hidden = false;
  show(saved === 'cal' ? 'cal' : 'list');
})();
