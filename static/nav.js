// Site menu: the Schools dropdown is a <details> element, so it opens and closes without this file.
// This only closes it when you click elsewhere or press Escape.
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.nav-drop[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll("details.nav-drop[open]").forEach(function (d) {
      d.removeAttribute("open");
      var s = d.querySelector("summary");
      if (s) s.focus();
    });
  });
})();

// Sponsor links in the footer: a Google Analytics event (sponsor_click, which sponsor) and a count for the daily
// usage report (/e beacon). The link opens normally either way.
document.addEventListener("click", function (e) {
  var a = e.target.closest && e.target.closest("a[data-sponsor]");
  if (!a) return;
  try { if (window.gtag) window.gtag("event", "sponsor_click", {sponsor: a.getAttribute("data-sponsor"), transport_type: "beacon"}); } catch (err) {}
  try { if (navigator.sendBeacon) navigator.sendBeacon("/e", "sponsor_click"); } catch (err) {}
});
