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
      if (!popup.hidden) body.innerHTML = html;   // our own server-escaped markup
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
      e.preventDefault();
      var person = tab.closest(".person");
      selectTab(person, tab.getAttribute("data-tab"), tab.href, !tab.closest(".popup"));
      return;
    }

    var yearLink = e.target.closest("a[data-tab-link]");
    if (yearLink) {
      var page = document.querySelector(".person");
      if (page) {
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
