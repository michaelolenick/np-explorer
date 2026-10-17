// Year tabs on person pages and the person popup on search results.
// Everything works without this file: tabs and names are plain links.
(function () {
  "use strict";

  // --- Year tabs --------------------------------------------------------------

  function selectTab(person, key, href, updateUrl) {
    person.querySelectorAll(".tabs a[data-tab]").forEach(function (a) {
      var on = a.getAttribute("data-tab") === key;
      a.classList.toggle("active", on);
      if (on) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    person.querySelectorAll(".tabpanel").forEach(function (p) {
      p.hidden = p.getAttribute("data-panel") !== key;
    });
    if (updateUrl && href) history.replaceState(null, "", href);
  }

  // --- Copy table -------------------------------------------------------------
  // Adds a "Copy table" button above each data table. Copies tab-separated text
  // that pastes into a spreadsheet as cells; money and counts become plain numbers.

  function cellText(cell) {
    // Action links ("view", "ProPublica") copy as their full URL.
    var hrefs = cell.querySelectorAll("a[data-copy-href]");
    if (hrefs.length) return Array.prototype.map.call(hrefs, function (a) { return a.href; }).join(" ");
    var c = cell.cloneNode(true);
    c.querySelectorAll(".muted, .raw, .tag, .count, button").forEach(function (n) { n.remove(); });
    var text = c.textContent.replace(/\s+/g, " ").trim();
    if (cell.classList.contains("n")) {
      // "$1,234" -> 1234, "-$5" -> -5, "-" -> empty
      if (text === "-") return "";
      var num = text.replace(/[$,]/g, "");
      if (/^-?\d+(\.\d+)?$/.test(num)) return num;
    }
    return text.replace(/\t/g, " ");
  }

  function tableToTSV(table) {
    var lines = [];
    table.querySelectorAll("tr").forEach(function (tr) {
      var cells = [];
      tr.querySelectorAll("th, td").forEach(function (cell) {
        cells.push(cellText(cell));
        for (var i = 1; i < (cell.colSpan || 1); i++) cells.push("");
      });
      if (cells.some(function (c) { return c !== ""; })) lines.push(cells.join("\t"));
    });
    return lines.join("\n") + "\n";
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      ta.remove();
      ok ? resolve() : reject(new Error("copy failed"));
    });
  }

  function addCopyButtons(root) {
    root.querySelectorAll(".scroll > table").forEach(function (table) {
      var wrap = table.parentElement;
      if (wrap.previousElementSibling && wrap.previousElementSibling.classList.contains("table-tools")) return;
      var tools = document.createElement("div");
      tools.className = "table-tools";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-table";
      btn.textContent = "Copy table";
      btn.title = "Copy as tab-separated text, ready to paste into a spreadsheet";
      tools.appendChild(btn);
      wrap.parentNode.insertBefore(tools, wrap);
    });
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".copy-table");
    if (!btn) return;
    var table = btn.parentElement.nextElementSibling.querySelector("table");
    copyText(tableToTSV(table)).then(function () {
      btn.textContent = "Copied";
      btn.classList.add("done");
    }, function () {
      btn.textContent = "Copy failed";
    }).then(function () {
      setTimeout(function () { btn.textContent = "Copy table"; btn.classList.remove("done"); }, 1500);
    });
  });

  addCopyButtons(document);

  // --- Popup ------------------------------------------------------------------

  var popup = document.getElementById("popup");
  var body = popup && popup.querySelector(".popup-body");
  var cache = new Map();
  var opener = null;

  function fragmentUrl(href) {
    return href + (href.indexOf("?") === -1 ? "?" : "&") + "fragment=1";
  }

  function load(href) {
    if (!cache.has(href)) {
      cache.set(href, fetch(fragmentUrl(href), { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      }).catch(function (e) {
        cache.delete(href);
        throw e;
      }));
    }
    return cache.get(href);
  }

  function openPopup(link) {
    opener = link;
    body.innerHTML = '<p class="muted">Loading&hellip;</p>';
    popup.hidden = false;
    document.documentElement.classList.add("popup-open");
    popup.querySelector(".popup-close").focus();
    load(link.href).then(function (html) {
      if (!popup.hidden) {
        body.innerHTML = html;   // our own server-escaped markup
        addCopyButtons(body);
      }
    }, function () {
      window.location.href = link.href;            // fall back to the full page
    });
  }

  function closePopup() {
    if (!popup || popup.hidden) return;
    popup.hidden = true;
    body.innerHTML = "";
    document.documentElement.classList.remove("popup-open");
    if (opener) opener.focus();
  }

  // --- Events -----------------------------------------------------------------

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

    var tab = e.target.closest(".tabs a[data-tab]");
    if (tab) {
      var person = tab.closest(".person");
      var key = tab.getAttribute("data-tab");
      // Big records render only the active year: other tabs load as normal links.
      if (!person.querySelector('.tabpanel[data-panel="' + key + '"]')) {
        if (tab.closest(".popup")) { e.preventDefault(); window.location.href = tab.href; }
        return;
      }
      e.preventDefault();
      selectTab(person, key, tab.href, !tab.closest(".popup"));
      return;
    }

    var yearLink = e.target.closest("a[data-tab-link]");
    if (yearLink) {
      var page = document.querySelector(".person");
      if (page && page.querySelector('.tabpanel[data-panel="' + yearLink.getAttribute("data-tab-link") + '"]')) {
        e.preventDefault();
        selectTab(page, yearLink.getAttribute("data-tab-link"), yearLink.href, true);
        page.querySelector(".tabs").scrollIntoView({ block: "start" });
      }
      return;
    }

    if (!popup) return;
    var name = e.target.closest("a[data-popup]");
    if (name) {
      e.preventDefault();
      openPopup(name);
      return;
    }
    if (e.target === popup || e.target.closest(".popup-close")) closePopup();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closePopup();
  });

  // Start fetching when the pointer or focus reaches a name, so the popup opens fast.
  function prefetch(e) {
    var name = e.target.closest && e.target.closest("a[data-popup]");
    if (name) load(name.href).catch(function () {});
  }
  if (popup) {
    document.addEventListener("pointerover", prefetch);
    document.addEventListener("focusin", prefetch);
  }
})();
