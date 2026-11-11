// News and Drugs live on the same page: switch between them without loading a
// new one. The address updates (index.html / drugs.html), so Back and links work.
(function () {
  var panels = document.querySelectorAll('[data-panel]');
  if (panels.length < 2) return;
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.folder[data-tab]'));
  var titles = { news: document.title.replace(/^Drugs · /, ''), drugs: 'Drugs · ' + document.title.replace(/^Drugs · /, '') };

  var slab = document.querySelector('.slab');
  function show(name) {
    if (slab) slab.dataset.theme = name;  // the page takes the selected tab's color
    panels.forEach(function (p) {
      var on = p.dataset.panel === name;
      p.hidden = !on;
      if (on) { p.classList.remove('enter'); void p.offsetWidth; p.classList.add('enter'); }  // replay the fade-in
    });
    tabs.forEach(function (t) {
      var on = t.dataset.tab === name;
      t.classList.toggle('on', on);
      if (on) t.setAttribute('aria-current', 'page'); else t.removeAttribute('aria-current');
    });
    document.title = titles[name];
  }

  tabs.forEach(function (t) {
    t.addEventListener('click', function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;  // new tab etc.
      e.preventDefault();
      if (t.classList.contains('on')) return;
      show(t.dataset.tab);
      history.pushState({ tab: t.dataset.tab }, '', t.getAttribute('href'));
    });
  });
  window.addEventListener('popstate', function () {
    show(/\/drugs(\.html)?$/.test(location.pathname) ? 'drugs' : 'news');
  });
})();
