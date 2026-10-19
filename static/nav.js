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
