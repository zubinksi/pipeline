// "New since your last visit": items found after this browser's previous visit get a
// small New tag. The visit time is kept in this browser only. On a first visit nothing
// is marked.
(function () {
  var KEY = 'readout-last-visit';
  var last = null;
  try { last = localStorage.getItem(KEY); } catch (e) { return; }
  if (last) {
    document.querySelectorAll('[data-found]').forEach(function (el) {
      if (el.dataset.found > last) {
        var tag = el.querySelector('.new-tag'); if (tag) tag.hidden = false;
        el.classList.add('is-new');
      }
    });
  }
  // remember this visit (a few seconds in, so a quick reload doesn't clear the marks)
  setTimeout(function () {
    try { localStorage.setItem(KEY, new Date().toISOString()); } catch (e) {}
  }, 4000);
})();
