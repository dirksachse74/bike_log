// Bike Log (PHP): small progressive enhancements. Every page also works without JavaScript.
(function () {
  'use strict';

  // confirmation before destructive forms
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (f.dataset && f.dataset.confirm && !window.confirm(f.dataset.confirm)) {
      e.preventDefault();
    }
  });

  // incident fix forms: "Replaced with" and "The old part" only when it was replaced
  document.querySelectorAll('[data-fix]').forEach(function (f) {
    var act = f.querySelector('[data-fix-action]');
    var sync = function () {
      f.querySelectorAll('[data-fix-for]').forEach(function (el) {
        var wrap = el.tagName === 'LABEL' ? el : el.closest('label');
        if (wrap) { wrap.hidden = el.getAttribute('data-fix-for') !== act.value; }
      });
    };
    act.addEventListener('change', sync);
    sync();
  });

  // maintenance form: offer only the actions that fit the chosen part, then its results
  var logForm = document.querySelector('[data-log-form]');
  if (logForm) {
    var data = JSON.parse(document.getElementById('log-data').textContent);
    var target = logForm.querySelector('[data-target]');
    var action = logForm.querySelector('[data-action]');
    var outcome = logForm.querySelector('[data-outcome]');
    var outWrap = logForm.querySelector('[data-outcome-wrap]');
    var measWrap = logForm.querySelector('[data-measure-wrap]');
    var symWrap = logForm.querySelector('[data-symptom-wrap]');
    var workWrap = logForm.querySelector('[data-work-wrap]');
    var unit = logForm.querySelector('[data-unit]');
    var ui = data.ui || {};
    var label = function (code, a) { return (a && a.labels && a.labels[code]) || code.charAt(0) + code.slice(1).toLowerCase().replace(/_/g, ' '); };
    var typeOf = function () { var v = target.value; return v.indexOf('b:') === 0 ? 'BIKE' : (data.types[v] || ''); };
    var fillActions = function () {
      var acts = data.actions[typeOf()] || {};
      var keep = action.value || data.pre;
      action.innerHTML = '';
      var first = document.createElement('option');
      first.value = ''; first.textContent = target.value ? (ui.choose || 'Choose...') : (ui.first || 'Choose the part first');
      action.appendChild(first);
      Object.keys(acts).forEach(function (code) {
        var o = document.createElement('option');
        o.value = code; o.textContent = acts[code].name;
        if (code === keep) { o.selected = true; }
        action.appendChild(o);
      });
      fillOutcome();
    };
    var fillOutcome = function () {
      var a = (data.actions[typeOf()] || {})[action.value];
      outcome.innerHTML = '';
      outWrap.hidden = !(a && a.outcomes.length);
      measWrap.hidden = !(a && a.measure);
      symWrap.hidden = !(a && a.symptom);
      workWrap.hidden = !(a && a.work_done);
      unit.textContent = a && a.unit ? '(' + a.unit + ')' : '';
      if (a && a.outcomes.length) {
        var blank = document.createElement('option');
        blank.value = ''; blank.textContent = a.measure ? (ui.measure || 'From the measurement') : (ui.choose || 'Choose...');
        outcome.appendChild(blank);
        a.outcomes.forEach(function (c) {
          var o = document.createElement('option'); o.value = c; o.textContent = label(c, a); outcome.appendChild(o);
        });
      }
    };
    target.addEventListener('change', fillActions);
    action.addEventListener('change', fillOutcome);
    fillActions();
  }
})();
