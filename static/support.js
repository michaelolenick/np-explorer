// Support page: "Other amount" opens a dialog asking how much.
// Works without this file: the Other button reloads the page with the same form shown inline.
(function () {
  "use strict";

  function open(d) {
    if (typeof d.showModal !== "function") return false;
    if (d.open) d.close();
    d.showModal();
    var input = d.querySelector("input[name=amount_dollars]");
    if (input) input.focus();
    return true;
  }

  document.addEventListener("click", function (e) {
    var b = e.target.closest("button.other-open");
    if (b) {
      var d = document.getElementById(b.getAttribute("data-dialog"));
      if (d && open(d)) e.preventDefault();
      return;
    }
    var c = e.target.closest("dialog .dialog-cancel");
    if (c) {
      var dlg = c.closest("dialog");
      if (dlg && typeof dlg.close === "function") {
        e.preventDefault();
        dlg.close();
      }
    }
  });

  // A dialog the server shows open (no-JavaScript fallback, or an amount out of range): make it a real dialog.
  document.querySelectorAll("dialog.other-amount[open]").forEach(open);
})();
