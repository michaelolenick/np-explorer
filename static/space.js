// Space folder page: a progress bar while files upload (owner, 2026-11-12: "when I click upload give me a status
// bar"). Works without this file: the form posts as usual and the page reloads when the upload is done.
(function () {
  "use strict";

  var form = document.querySelector("form.space-upload");
  if (!form || typeof XMLHttpRequest === "undefined" || typeof FormData === "undefined") return;
  var box = document.getElementById("sp-progress");
  var bar = box && box.querySelector("progress");
  var text = box && box.querySelector(".sp-progress-text");
  var button = form.querySelector("button[type=submit]");

  function mb(n) { return (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB"; }

  function say(s) { if (text) text.textContent = s; }

  form.addEventListener("submit", function (e) {
    var input = form.querySelector("input[type=file]");
    if (!input || !input.files || !input.files.length) return;      // the browser's own "required" message
    e.preventDefault();
    var total = 0, i;
    for (i = 0; i < input.files.length; i++) total += input.files[i].size;
    var files = input.files.length;
    if (box) box.hidden = false;
    if (bar) { bar.max = 100; bar.value = 0; }
    say("Uploading " + files + " file" + (files === 1 ? "" : "s") + " (" + mb(total) + ")…");
    if (button) { button.disabled = true; button.textContent = "UPLOADING…"; }

    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.getAttribute("action"), true);
    xhr.responseType = "text";
    xhr.upload.addEventListener("progress", function (ev) {
      if (!ev.lengthComputable) return;
      var pct = Math.round(ev.loaded * 100 / ev.total);
      if (bar) bar.value = pct;
      say(pct < 100 ? "Uploading: " + pct + "% (" + mb(ev.loaded) + " of " + mb(ev.total) + ")"
                    : "Upload sent; storing " + mb(ev.total) + "… (the page reloads when it is stored)");
    });
    xhr.addEventListener("load", function () {
      if (xhr.status >= 200 && xhr.status < 400) {
        if (bar) bar.value = 100;
        say("Stored. Reloading…");
        // The server answers the POST with a redirect to the folder page; go where it went.
        window.location.href = xhr.responseURL || window.location.pathname;
      } else {
        fail("The server answered " + xhr.status + ". Nothing was stored; please try again.");
      }
    });
    xhr.addEventListener("error", function () { fail("The upload failed (connection lost?). Please try again."); });
    xhr.addEventListener("abort", function () { fail("Upload cancelled."); });
    xhr.send(new FormData(form));
  });

  function fail(msg) {
    say(msg);
    if (bar) bar.value = 0;
    if (button) { button.disabled = false; button.textContent = "UPLOAD"; }
  }
})();
