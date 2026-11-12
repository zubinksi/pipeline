// The cabinet: what you follow. Saved in this browser as
//   {v: 2, topics: [...], companies: [...], off: [...]}
// A drug shows if its topic or one of its companies is followed, and it isn't
// switched off. With nothing saved, every topic is followed. On the cabinet page
// the checkboxes edit this; on other pages, rows for drugs (and topic news) you
// don't follow are hidden (data-untracked tells filter.js to leave them hidden).
(function () {
  var KEY = 'cabinet';
  var data = {};
  try { data = JSON.parse(document.getElementById('cabinet-data').textContent); } catch (e) { return; }
  var drugs = data.drugs || {}, ids = Object.keys(drugs);

  function load() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY));
      if (v && v.v === 2) return { topics: v.topics || [], companies: v.companies || [], off: v.off || [] };
    } catch (e) {}
    return null;
  }
  function save(s) {
    try { localStorage.setItem(KEY, JSON.stringify({ v: 2, topics: s.topics, companies: s.companies, off: s.off })); } catch (e) {}
  }
  var saved = load();
  var welcome = !saved && /[?&]welcome\b/.test(location.search);
  // first visit: start with nothing chosen; otherwise, with nothing saved, everything is followed
  var st = saved || (welcome ? { topics: [], companies: [], off: [] }
                             : { topics: (data.topics || []).slice(), companies: [], off: [] });
  function has(a, x) { return a.indexOf(x) !== -1; }
  function add(a, x) { if (!has(a, x)) a.push(x); }
  function drop(a, x) { var i = a.indexOf(x); if (i !== -1) a.splice(i, 1); }
  function shown(id) {
    var d = drugs[id]; if (!d) return true;
    var on = has(st.topics, d.t) || d.c.some(function (c) { return has(st.companies, c); });
    return on && !has(st.off, id);
  }
  function viaCompany(id) { return drugs[id].c.some(function (c) { return has(st.companies, c); }); }
  function inTopic(t) { return ids.filter(function (id) { return drugs[id].t === t; }); }
  function topicShown(t) { return has(st.topics, t) || ids.some(function (id) { return drugs[id].t === t && shown(id); }); }

  var form = document.querySelector('[data-cabinet]');
  if (form) {
    var q = function (sel) { return Array.prototype.slice.call(form.querySelectorAll(sel)); };
    function sync() {
      q('[data-drug-box]').forEach(function (b) { b.checked = shown(b.dataset.drugBox); });
      q('[data-topic-box]').forEach(function (b) {
        var all = inTopic(b.dataset.topicBox), n = all.filter(shown).length;
        b.checked = n === all.length && n > 0;
        b.indeterminate = n > 0 && n < all.length;
        var drawer = b.closest('.cab-drawer'), lab = drawer.querySelector('[data-shown]');
        if (lab) lab.textContent = n;
        drawer.classList.toggle('off', n === 0);
      });
      q('[data-set-box]').forEach(function (b) {
        var set = b.dataset.setBox.split(' '), n = set.filter(shown).length;
        b.checked = n === set.length; b.indeterminate = n > 0 && n < set.length;
      });
      q('[data-company-box]').forEach(function (b) { b.checked = has(st.companies, b.dataset.companyBox); });
      var any = ids.some(shown);
      done.classList.toggle('disabled', !any);
      done.setAttribute('aria-disabled', String(!any));
      if (need) need.hidden = any;
    }
    // switch a set of drugs (a topic, or part of one) on or off together
    function toggleSet(set, t) {
      if (set.some(shown)) {
        set.forEach(function (id) { if (shown(id)) add(st.off, id); });
        if (!inTopic(t).some(shown)) {  // nothing left: unfollow the topic, keeping company-followed drugs off
          drop(st.topics, t);
          inTopic(t).forEach(function (id) { if (!viaCompany(id)) drop(st.off, id); });
        }
      } else {
        var before = inTopic(t).filter(shown);
        add(st.topics, t);
        inTopic(t).forEach(function (id) { if (!has(set, id) && !has(before, id)) add(st.off, id); });
        set.forEach(function (id) { drop(st.off, id); });
      }
    }
    var done = document.querySelector('[data-done]'), need = document.querySelector('.cab-need');
    if (welcome) {
      document.querySelector('.cab-welcome').hidden = false;
      document.querySelector('.cab-usual').hidden = true;
      done.textContent = 'Start reading';
    }
    done.addEventListener('click', function (e) {
      if (!ids.some(shown)) { e.preventDefault(); if (need) need.hidden = false; return; }
      save(st);  // even if nothing was changed, so the welcome isn't shown again
    });
    form.addEventListener('change', function (e) {
      var b = e.target;
      if (b.dataset.topicBox) {
        toggleSet(inTopic(b.dataset.topicBox), b.dataset.topicBox);
      } else if (b.dataset.setBox) {
        toggleSet(b.dataset.setBox.split(' '), b.dataset.setTopic);
      } else if (b.dataset.drugBox) {
        var id = b.dataset.drugBox, d = drugs[id];
        if (shown(id)) add(st.off, id);
        else {
          drop(st.off, id);
          if (!shown(id)) {  // its topic wasn't followed: follow it, but only for this drug
            var before = inTopic(d.t).filter(shown);
            add(st.topics, d.t);
            inTopic(d.t).forEach(function (x) { if (x !== id && !has(before, x)) add(st.off, x); });
          }
        }
      } else if (b.dataset.companyBox) {
        var c = b.dataset.companyBox;
        if (has(st.companies, c)) drop(st.companies, c);
        else {
          add(st.companies, c);
          ids.forEach(function (x) { if (has(drugs[x].c, c)) drop(st.off, x); });
        }
      }
      save(st); sync();
    });
    q('.cab-more').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var list = document.getElementById(btn.getAttribute('aria-controls'));
        var open = list.hidden;
        list.hidden = !open;
        btn.setAttribute('aria-expanded', String(open));
      });
    });
    sync();
    return;
  }
  if (!saved) return;  // following everything: nothing to hide

  function hide(el) { el.hidden = true; el.dataset.untracked = '1'; }
  document.querySelectorAll('.chip[data-k="tp"]').forEach(function (c) {
    if (c.dataset.v !== 'all' && !topicShown(c.dataset.v)) c.remove();
  });
  document.querySelectorAll('[data-drug]').forEach(function (el) { if (!shown(el.dataset.drug)) hide(el); });
  document.querySelectorAll('[data-topic]').forEach(function (el) { if (!topicShown(el.dataset.topic)) hide(el); });
  // tidy up: group and topic counts, empty groups and sections, the total
  document.querySelectorAll('[data-group]').forEach(function (g) {
    var n = g.querySelectorAll('.drug:not([data-untracked])').length;
    g.querySelector('[data-count]').textContent = n;
    g.hidden = n === 0;
  });
  document.querySelectorAll('[data-topic-sec]').forEach(function (s) {
    var n = s.querySelectorAll('.drug:not([data-untracked])').length;
    var c = s.querySelector('[data-tcount]'); if (c) c.textContent = n;
    if (!n) { s.hidden = true; s.dataset.untracked = '1'; }
  });
  document.querySelectorAll('[data-filter], .section').forEach(function (sec) {
    if (!sec.querySelector('.dtable')) return;
    var n = sec.querySelectorAll('.drug:not([data-untracked])').length;
    var total = sec.querySelector('[data-total]'); if (total) total.textContent = n;
    var empty = sec.querySelector('.cab-empty'); if (empty) empty.hidden = n > 0;
    if (!n) { var f = sec.querySelector('.ficon'); if (f) f.remove(); }
  });
  document.querySelectorAll('.tl-list, .section').forEach(function (l) {
    var sec = l.closest('.section') || l;
    var items = sec.querySelectorAll('.tl, .change');
    if (items.length && !sec.querySelector('.tl:not([hidden]), .change:not([hidden])') && !sec.querySelector('.dtable, .weekline')) sec.hidden = true;
  });
})();
