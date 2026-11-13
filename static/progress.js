/* A status bar whenever a query runs longer than 0.2 s (owner, 2026-11-13): searches submitted from any form,
   links into search, ask, deep-query, leaderboard and census pages, and in-page requests (the short answer, the
   deep-query poll). The bar sits at the top of the page with the elapsed time and goes away when the next page
   arrives (or the request ends). No inline script: the CSP allows only files like this one. */
(function () {
  "use strict";
  var SHOW_AFTER = 200, bar, text, timer, tick, t0, pending = 0;
  function ensure() {
    if (bar) return;
    bar = document.createElement("div");
    bar.className = "np-progress";
    bar.setAttribute("role", "status");
    bar.setAttribute("aria-live", "polite");
    bar.hidden = true;
    bar.innerHTML = '<div class="np-progress-bar"></div><span class="np-progress-text"></span>';
    document.body.appendChild(bar);
    text = bar.querySelector(".np-progress-text");
  }
  function show(label) {
    ensure();
    bar.hidden = false;
    clearInterval(tick);
    var paint = function () {
      var s = (Date.now() - t0) / 1000;
      text.textContent = label + " " + (s < 10 ? s.toFixed(1) : Math.round(s)) + " s";
    };
    paint();
    tick = setInterval(paint, 100);
  }
  function hide() {
    clearTimeout(timer);
    clearInterval(tick);
    if (bar) bar.hidden = true;
  }
  function arm(label) {
    clearTimeout(timer);
    t0 = Date.now();
    timer = setTimeout(function () { show(label); }, SHOW_AFTER);
  }
  // a search form going off (GET forms: the home box, /search, /ask, the filters)
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (f && f.tagName === "FORM" && (f.method || "get").toLowerCase() === "get") arm("Searching…");
  });
  // a link into a page that runs a query
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    var h = a.getAttribute("href") || "";
    if (/^\/(search|ask|deep|boards|census|nearby|topics|dreamer|categories|org|person|institution|ipos|form5500|recalls)(\/|\?|$)/.test(h)
        && !/\.(csv|json|geojson|svg|png)(\?|$)/.test(h)) arm("Loading…");
  });
  // in-page requests: the short answer being written, deep-query polling, uploads
  if (window.fetch) {
    var orig = window.fetch;
    window.fetch = function () {
      var p = orig.apply(this, arguments);
      pending += 1;
      if (pending === 1) arm("Working…");
      var done = function () { pending = Math.max(0, pending - 1); if (pending === 0) hide(); };
      p.then(done, done);
      return p;
    };
  }
  window.addEventListener("pageshow", hide);   // back/forward from the cache: nothing is loading
  window.addEventListener("pagehide", hide);
})();
