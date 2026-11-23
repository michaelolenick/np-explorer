/* Public-records request creator (app/foia.py). Same-origin script: the CSP allows no inline code.
   Steps with Back/Next, a live letter preview from POST /api/foia/letter, and "Expand with AI" per text box. */
(function () {
  var root = document.getElementById("foia");
  if (!root) return;
  var $ = function (id) { return document.getElementById(id); };
  var qa = function (sel, el) { return Array.prototype.slice.call((el || root).querySelectorAll(sel)); };
  var STATES = JSON.parse(root.getAttribute("data-states") || "{}");
  var PRESETS = JSON.parse(root.getAttribute("data-agencies") || "{}");
  var steps = qa(".foia-step");
  var S = { step: 1, kind: root.getAttribute("data-kind") || "federal", ein: "", org: null, awards: [], picked: {}, timer: null, seq: 0 };
  var startAward = root.getAttribute("data-award") || "";

  function kind() { var r = qa('input[name="kind"]:checked')[0]; return r ? r.value : S.kind; }

  function show(n) {
    S.step = Math.max(1, Math.min(5, n));
    steps.forEach(function (el) { el.hidden = Number(el.getAttribute("data-step")) !== S.step; });
    qa("#foia-steps li").forEach(function (li, i) {
      li.className = i + 1 === S.step ? "on" : (i + 1 < S.step ? "done" : "");
    });
    $("foia-back").disabled = S.step === 1;
    $("foia-next").hidden = S.step === 5;
    $("foia-pos").textContent = "Step " + S.step + " of 5";
    applyKind();
    if (S.step === 5) preview(true);
    window.scrollTo(0, root.offsetTop - 10);
  }

  function applyKind() {
    var k = kind();
    qa("[data-for]").forEach(function (el) {
      el.hidden = (" " + el.getAttribute("data-for") + " ").indexOf(" " + k + " ") < 0;
    });
    var sec = qa('[data-step="3"] fieldset[data-for]');
    sec.forEach(function (f) { f.hidden = f.getAttribute("data-for") !== k; });
  }

  function validate() {
    if (S.step === 2 && !S.org) { alert_(" Pick an organization first."); return false; }
    return true;
  }
  function alert_(m) { var n = $("foia-pos"); n.textContent = m.trim(); }

  // ---- organization ----------------------------------------------------------------------------------------------
  function chooseOrg(ein) {
    return fetch("/api/foia/context?ein=" + encodeURIComponent(ein)).then(function (r) { return r.ok ? r.json() : null; }).then(function (c) {
      if (!c) return;
      S.org = c.org; S.ein = c.org.ein; S.awards = c.awards; S.picked = {};
      var chosen = $("foia-org-chosen");
      chosen.hidden = false;
      chosen.textContent = "";
      var b = document.createElement("strong"); b.textContent = c.org.name; chosen.appendChild(b);
      chosen.appendChild(document.createTextNode(" (EIN " + c.org.ein.slice(0, 2) + "-" + c.org.ein.slice(2) + ") " + [c.org.city, c.org.state].filter(Boolean).join(", ") + " "));
      var ch = document.createElement("button"); ch.type = "button"; ch.className = "plain"; ch.textContent = "Change";
      ch.addEventListener("click", function () { S.org = null; chosen.hidden = true; $("foia-org-find").hidden = false; });
      chosen.appendChild(ch);
      $("foia-org-find").hidden = true;
      var first = null;
      c.awards.forEach(function (a) { if (a.key === startAward) first = a; });
      if (!first && c.awards.length) first = c.awards[0];
      if (first) {
        $("foia-agency").value = first.route;
        c.awards.forEach(function (a) {
          if (startAward ? a.key === startAward : a.route === first.route) S.picked[a.key] = true;
        });
        if (startAward && first.key === startAward) $("foia-agency").value = first.route;
      }
      renderAwards();
    });
  }

  function money(n) { return n ? "$" + Math.round(n).toLocaleString("en-US") : ""; }

  function renderAwards() {
    var t = $("foia-awards"), body = t.querySelector("tbody"), note = $("foia-awards-note");
    body.textContent = "";
    if (!S.awards.length) {
      t.hidden = true;
      note.textContent = "FURP has no federal award data linked to this organization. Pick the agency yourself below, and list any award numbers you know.";
      return;
    }
    note.textContent = "Awards FURP links to this organization by name and zip code (USAspending). Tick the ones the request is about; the agency is chosen for you and you can change it.";
    t.hidden = false;
    S.awards.forEach(function (a) {
      var tr = document.createElement("tr");
      var td = document.createElement("td"), cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !!S.picked[a.key];
      cb.addEventListener("change", function () {
        S.picked[a.key] = cb.checked;
        if (cb.checked) $("foia-agency").value = a.route;
        changed();
      });
      td.appendChild(cb); tr.appendChild(td);
      var d = document.createElement("td");
      d.appendChild(document.createTextNode((a.number || a.key) + " "));
      if (a.title) { var m = document.createElement("span"); m.className = "muted"; m.textContent = a.title; d.appendChild(m); }
      tr.appendChild(d);
      [a.sub_agency || a.agency || "", (a.y0 === a.y1 ? a.y0 : a.y0 + "-" + a.y1) || ""].forEach(function (v) {
        var c = document.createElement("td"); c.textContent = v; tr.appendChild(c);
      });
      var n = document.createElement("td"); n.className = "n"; n.textContent = money(a.amount); tr.appendChild(n);
      body.appendChild(tr);
    });
  }

  var findTimer = null;
  $("foia-org-q").addEventListener("input", function () {
    clearTimeout(findTimer);
    var q = this.value;
    findTimer = setTimeout(function () {
      fetch("/api/foia/orgs?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (rows) {
        var ul = $("foia-org-results"); ul.textContent = "";
        rows.forEach(function (o) {
          var li = document.createElement("li"), b = document.createElement("button");
          b.type = "button"; b.className = "plain"; b.textContent = o.name + " (" + [o.city, o.state].filter(Boolean).join(", ") + ")";
          b.addEventListener("click", function () { ul.textContent = ""; chooseOrg(o.ein).then(changed); });
          li.appendChild(b); ul.appendChild(li);
        });
      }).catch(function () {});
    }, 250);
  });

  // ---- state presets ---------------------------------------------------------------------------------------------
  function statePresets() {
    var code = $("foia-state").value, box = $("foia-state-presets");
    box.textContent = "";
    (PRESETS[code] || []).forEach(function (p) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = "Use: " + p[0];
      b.addEventListener("click", function () { $("foia-agency-name").value = p[1]; $("foia-program").value = p[2]; changed(); });
      box.appendChild(b);
    });
    var st = STATES[code];
    if (st) {
      var p = document.createElement("p"); p.className = "muted";
      p.textContent = st.statute + " (" + st.citation + "). Who may ask: " + st.who + ".";
      box.appendChild(p);
    }
  }

  // ---- the letter ------------------------------------------------------------------------------------------------
  function params() {
    var k = kind();
    var awards = S.awards.filter(function (a) { return S.picked[a.key]; }).map(function (a) { return a.key; });
    return {
      kind: k, ein: S.ein, agency: $("foia-agency").value, state: $("foia-state").value,
      agency_name: $("foia-agency-name").value, program: $("foia-program").value, awards: awards,
      manual_awards: $("foia-manual").value,
      records: qa('input[name="rec-' + k + '"]:checked').map(function (c) { return c.value; }),
      also: $("foia-also").value, date_from: $("foia-from").value, date_to: $("foia-to").value,
      electronic: $("foia-electronic").checked,
      fee_category: (qa('input[name="fee"]:checked')[0] || {}).value || "other",
      fee_waiver: $("foia-waiver").checked, purpose: $("foia-purpose").value,
      expedite: k === "federal" && $("foia-expedite").checked, expedite_reason: $("foia-expedite-reason").value,
      fee_limit: $("foia-feelimit").value,
      requester: { name: $("foia-name").value, email: $("foia-email").value, address: $("foia-addr").value,
                   org: $("foia-reqorg").value, phone: $("foia-phone").value }
    };
  }

  function changed() { if (S.step === 5) preview(false); }

  function preview(now) {
    clearTimeout(S.timer);
    var go = function () {
      var id = ++S.seq;
      fetch("/api/foia/letter", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(params()) })
        .then(function (r) { return r.json(); }).then(function (d) {
          if (id !== S.seq) return;
          $("foia-letter").value = d.text || "";
          var w = $("foia-warn"); w.textContent = "";
          (d.warnings || []).forEach(function (m) { var li = document.createElement("li"); li.textContent = m; w.appendChild(li); });
          sendBox(d.send || {}, d.text || "");
        });
    };
    if (now) go(); else S.timer = setTimeout(go, 300);
  }

  function row(box, label, val, href) {
    if (!val) return;
    var p = document.createElement("p"), b = document.createElement("strong");
    b.textContent = label + ": "; p.appendChild(b);
    if (href) { var a = document.createElement("a"); a.href = href; a.rel = "noopener"; a.textContent = val; p.appendChild(a); }
    else p.appendChild(document.createTextNode(val));
    box.appendChild(p);
  }
  function safeUrl(u) { return /^https?:\/\//.test(u || "") ? u : null; }

  function sendBox(s, text) {
    var box = $("foia-send"); box.textContent = "";
    var h = document.createElement("h3"); h.textContent = "Where to send it"; box.appendChild(h);
    row(box, "To", s.to);
    if (s.email && /^[^\s@(]+@[^\s@(]+\.[a-z]+$/i.test(s.email)) row(box, "Email", s.email, "mailto:" + s.email);
    else row(box, "Email", s.email);
    row(box, "Portal", s.portal, safeUrl(s.portal));
    row(box, "Mail", s.address);
    row(box, "Note", s.note);
    if (s.source) row(box, "Source of this contact", s.source, safeUrl(s.source));
    if (!s.verified) row(box, "Heads up", "This contact is not confirmed. Check it before you send" + (s.find ? ": " + s.find : "."), safeUrl(s.find));
    var m = $("foia-mailto");
    if (s.email && /^[^\s@(]+@[^\s@(]+\.[a-z]+$/i.test(s.email)) {
      var href = "mailto:" + s.email + "?subject=" + encodeURIComponent(s.subject || "Records request");
      if (text.length < 1500) href += "&body=" + encodeURIComponent(text);
      m.href = href; m.hidden = false;
    } else m.hidden = true;
  }

  $("foia-copy").addEventListener("click", function () {
    var ta = $("foia-letter"), msg = $("foia-copied");
    var done = function () { msg.textContent = "Copied."; setTimeout(function () { msg.textContent = ""; }, 2500); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(ta.value).then(done, function () { ta.select(); document.execCommand("copy"); done(); });
    else { ta.select(); document.execCommand("copy"); done(); }
  });

  // ---- Expand with AI --------------------------------------------------------------------------------------------
  qa(".foia-expand").forEach(function (btn) {
    var ta = $(btn.getAttribute("data-target")), undo = qa('.foia-undo[data-target="' + btn.getAttribute("data-target") + '"]')[0],
        msg = qa('.foia-ai-msg[data-target="' + btn.getAttribute("data-target") + '"]')[0], before = "";
    btn.addEventListener("click", function () {
      var text = ta.value.trim();
      if (text.length < 4) { msg.textContent = "Type a few words first."; return; }
      before = ta.value; btn.disabled = true; msg.textContent = "Working...";
      fetch("/api/foia/expand", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ field: btn.getAttribute("data-field"), text: text, context: { org: S.org ? S.org.name : "", kind: kind(), agency: kind() === "state" ? $("foia-agency-name").value : "" } }) })
        .then(function (r) { return r.json(); }).then(function (d) {
          if (d.text) { ta.value = d.text; undo.hidden = false; msg.textContent = "Expanded. Read it and edit it: it is your request."; changed(); }
          else msg.textContent = d.error || "Could not expand it.";
        }).catch(function () { msg.textContent = "Could not reach the AI helper."; }).then(function () { btn.disabled = false; });
    });
    undo.addEventListener("click", function () { ta.value = before; undo.hidden = true; msg.textContent = ""; changed(); });
  });

  // ---- wiring ----------------------------------------------------------------------------------------------------
  $("foia-back").addEventListener("click", function () { show(S.step - 1); });
  $("foia-next").addEventListener("click", function () { if (validate()) show(S.step + 1); });
  $("foia-expedite").addEventListener("change", function () { $("foia-expedite-box").hidden = !this.checked; changed(); });
  $("foia-state").addEventListener("change", function () { statePresets(); changed(); });
  qa('input[name="kind"]').forEach(function (r) { r.addEventListener("change", function () { S.kind = r.value; applyKind(); }); });
  root.addEventListener("input", changed);
  root.addEventListener("change", changed);

  var init = qa('input[name="kind"][value="' + S.kind + '"]')[0] || qa('input[name="kind"]')[0];
  init.checked = true;
  $("foia-state").value = "TX";
  statePresets();
  var ein = root.getAttribute("data-ein");
  if (ein) chooseOrg(ein).then(function () { show(2); });
  else show(1);
})();
