/* FourWells front end.
 *
 * Plain ES modules-free JavaScript against the JSON API in app.py. No build
 * step on purpose: the whole project's demo property is that it runs on a
 * laptop with no install, and a bundler would trade that away.
 *
 * Three pages behind a tiny history-API router: Overview, Runs (and one run),
 * and the Call log. Everything polls while "live" is ticked, so a run landing
 * on disk shows up without a reload.
 */
(function () {
  "use strict";

  var view = document.getElementById("view");
  var pulse = document.getElementById("pulse");
  var auto = document.getElementById("autorefresh");
  var timer = null;
  var state = { calls: [], callsTotal: 0, sort: {}, open: {} };

  // ---------------------------------------------------------------- utils
  function el(html) { var d = document.createElement("div"); d.innerHTML = html; return d; }
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s === null || s === undefined ? "" : s;
    return d.innerHTML;
  }
  function num(v, dp) {
    if (v === null || v === undefined) return "—";
    return (+v).toFixed(dp === undefined ? 2 : dp);
  }
  function ms(v) {
    if (v === null || v === undefined) return "—";
    return v >= 1000 ? (v / 1000).toFixed(2) + " s" : (+v).toFixed(1) + " ms";
  }
  function pretty(v) {
    if (v === null || v === undefined) return "(none)";
    if (typeof v === "string") return v;
    try { return JSON.stringify(v, null, 2); } catch (e) { return String(v); }
  }
  function get(url) {
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error(url + " → HTTP " + r.status);
        return r.json();
      });
  }
  function blink() {
    pulse.classList.add("on");
    setTimeout(function () { pulse.classList.remove("on"); }, 400);
  }
  function fail(e) {
    view.innerHTML =
      '<div class="note bad"><h3>Could not load</h3><p>' + esc(e.message) +
      "</p><p class=muted>The server is at the address in your terminal. " +
      "If you restarted it, it may be on a different port.</p></div>";
  }

  // ---------------------------------------------------------------- router
  var routes = [
    { re: /^\/experiments$/, page: function () { return window.antibodyWorkspace("list"); } },
    { re: /^\/experiments\/([^/]+)$/, page: function (id) { return window.antibodyWorkspace("detail", id); } },
    { re: /^\/compare$/, page: function () { return window.antibodyWorkspace("compare"); } },
    { re: /^\/$/, page: overview },
    { re: /^\/runs$/, page: runsList },
    { re: /^\/runs\/([^/]+)$/, page: runDetail },
    { re: /^\/logs$/, page: callLog }
  ];

  function go(path, push) {
    if (push !== false && path !== location.pathname) history.pushState({}, "", path);
    document.querySelectorAll("nav a").forEach(function (a) {
      var h = a.getAttribute("data-nav");
      a.classList.toggle("on", h === path || (h === "/runs" && path.indexOf("/runs") === 0));
    });
    for (var i = 0; i < routes.length; i++) {
      var m = path.match(routes[i].re);
      if (m) { current = { fn: routes[i].page, arg: m[1] }; return current.fn(m[1]); }
    }
    view.innerHTML = '<div class="note"><h3>No such page</h3><p>' + esc(path) +
      '</p><p><a href="/">Back to the overview</a></p></div>';
  }
  var current = null;

  document.addEventListener("click", function (e) {
    var a = e.target.closest("a");
    if (!a || a.target === "_blank") return;
    var href = a.getAttribute("href") || "";
    if (href.charAt(0) !== "/" || href.indexOf("/api/") === 0 ||
        href.indexOf("/static/") === 0) return;
    e.preventDefault();
    go(href);
  });
  window.addEventListener("popstate", function () { go(location.pathname, false); });

  // ---------------------------------------------------------------- overview
  function overview() {
    return get("/api/overview").then(function (d) {
      blink();
      var c = d.calls || {};
      var h = "<h1>Overview</h1>";
      h += '<p class="muted">' + d.runs + " run(s) on disk · " +
           (c.calls || 0) + " logged calls</p>";

      if (!d.latest) {
        h += '<div class="note"><h3>No runs yet</h3><p>Run <code>make demo</code> ' +
             "in the project directory. This page picks it up on its own.</p></div>";
        view.innerHTML = h;
        return;
      }

      var k = d.latest.counts;
      h += "<h2>Latest run</h2>";
      h += '<p class="muted"><code>' + esc(d.latest.run_id) + "</code> · " +
           esc(d.latest.target || "") + " · " + num(d.latest.seconds, 2) + " s</p>";
      h += '<div class="cards">' +
        card(k.generated, "candidates") +
        card(k.passed, "cleared gates") +
        card(k.submitted + " / " + k.cap, "preview shortlist") +
        card(k.lab_slots, "preview picks") +
        card(k.stub, "stub records", k.stub ? "warn" : "") +
        "</div>";

      (d.latest.warnings || []).forEach(function (w) {
        h += '<div class="note warn">' + esc(w) + "</div>";
      });

      h += '<p><a href="/runs/' + encodeURIComponent(d.latest.run_id) +
           '">Open this run →</a></p>';

      h += "<h2>Calls</h2>";
      if (!c.calls) {
        h += '<div class="note"><p>Nothing in the call log yet. The pipeline runs ' +
             "offline against stub designs, so it makes no API calls — the log " +
             "fills up once a real provider is wired in.</p></div>";
      } else {
        h += '<div class="cards">' +
          card(c.calls, "calls") +
          card(ms(c.total_ms), "total time") +
          card(c.errors, "errors", c.errors ? "bad" : "") +
          card(c.cache_hits, "cache hits", c.cache_hits ? "good" : "") +
          card(c.offline_blocked, "offline blocked", c.offline_blocked ? "warn" : "") +
          card(ms(c.p95_ms), "p95") +
          "</div>";
        h += '<p><a href="/logs">Open the call log →</a></p>';
      }
      view.innerHTML = h;
    }).catch(fail);
  }

  function card(value, label, cls) {
    return '<div class="card' + (cls ? " " + cls : "") + '"><b>' + esc(value) +
           "</b><span>" + esc(label) + "</span></div>";
  }

  // ---------------------------------------------------------------- runs
  function runsList() {
    return get("/api/runs").then(function (d) {
      blink();
      var h = "<h1>Runs</h1>";
      if (!d.runs.length) {
        h += '<p class="empty">No runs yet. Run <code>make demo</code>.</p>';
        view.innerHTML = h; return;
      }
      h += '<p class="muted">' + d.runs.length + " run(s), newest first.</p>";
      h += '<div class="panel"><table><thead><tr><th class="plain">Run</th>' +
           '<th class="plain">Target</th><th class="plain n">Seed</th>' +
           '<th class="plain n">Stages</th><th class="plain n">Time</th>' +
           '<th class="plain">Warnings</th><th class="plain">Commit</th>' +
           "</tr></thead><tbody>";
      d.runs.forEach(function (r) {
        h += '<tr class="clickable" data-go="/runs/' + encodeURIComponent(r.run_id) +
          '"><td><code>' + esc(r.run_id) + "</code></td>" +
          "<td>" + esc(r.target || "—") + "</td>" +
          '<td class="n">' + esc(r.seed) + "</td>" +
          '<td class="n">' + r.stages.length + "</td>" +
          '<td class="n">' + num(r.seconds, 2) + " s</td>" +
          "<td>" + (r.warnings.length
            ? '<span class="st offline_blocked">' + r.warnings.length + "</span>" : "") + "</td>" +
          "<td><code>" + esc((r.git_sha || "").slice(0, 10)) + "</code></td></tr>";
      });
      h += "</tbody></table></div>";
      view.innerHTML = h;
      wireRowNav();
    }).catch(fail);
  }

  function wireRowNav() {
    view.querySelectorAll("tr[data-go]").forEach(function (tr) {
      tr.addEventListener("click", function () { go(tr.getAttribute("data-go")); });
    });
  }

  function runDetail(id) {
    return get("/api/runs/" + encodeURIComponent(id)).then(function (d) {
      blink();
      if (d.error) { view.innerHTML = '<div class="note bad">' + esc(d.error) + "</div>"; return; }
      var k = d.counts, cfg = d.config || {};
      var h = '<p class="muted"><a href="/runs">← all runs</a></p>';
      h += "<h1>" + esc(d.run_id) + "</h1>";
      h += '<p class="muted">' + esc(cfg.target || "") + " · reference " +
           esc(cfg.reference || "") + " · seed " + esc(cfg.seed) +
           " · commit <code>" + esc((cfg.git_sha || "").slice(0, 10)) + "</code>" +
           (d.has_report ? ' · <a href="/api/report/' + encodeURIComponent(d.run_id) +
             '" target="_blank">generated report</a>' : "") + "</p>";

      h += '<div class="cards">' +
        card(k.generated, "candidates") + card(k.passed, "cleared gates") +
        card(k.submitted + " / " + k.cap, "preview shortlist") +
        card(k.lab_slots, "preview picks") +
        card(k.stub, "stub", k.stub ? "warn" : "") + "</div>";

      (cfg.warnings || []).forEach(function (w) {
        h += '<div class="note warn">' + esc(w) + "</div>";
      });

      h += '<div class="note warn"><p><strong>Legacy heuristic preview.</strong> ' +
        "These normalized sequence scores are not calibrated probabilities. The legacy " +
        "stability proxy is developability evidence, not thermostability. Preview tiers " +
        "and products do not establish experimental performance. Use " +
        '<a href="/experiments">Experiments</a> for evidence, official validation and exports.</p></div>';

      if (Object.keys(d.failed_rules).length) {
        h += "<h2>Why candidates were rejected</h2><div class=panel><table>" +
          '<thead><tr><th class="plain">Rule</th><th class="plain n">Designs</th>' +
          "</tr></thead><tbody>";
        Object.keys(d.failed_rules).forEach(function (r) {
          h += "<tr><td>" + esc(r) + '</td><td class="n">' + d.failed_rules[r] + "</td></tr>";
        });
        h += "</tbody></table></div>";
      }

      h += "<h2>The submission</h2>";
      h += '<div class="controls">' +
        '<input type="search" id="dq" placeholder="Search id, CDRH3, cluster…">' +
        '<button class="btn" id="dlab" aria-pressed="false">Lab slots only</button>' +
        '<span class="muted" id="dcount"></span></div>';
      h += '<div class="panel" id="dtable"></div>';
      view.innerHTML = h;

      var rows = d.shortlist, axes = d.axes;
      var sortK = "rank", sortA = true, labOnly = false, openId = null;

      function visible() {
        var q = (document.getElementById("dq").value || "").trim().toLowerCase();
        return rows.filter(function (r) {
          if (labOnly && !r.lab) return false;
          if (!q) return true;
          return (r.design_id + " " + (r.cdrh3 || "") + " " + (r.cluster || "") + " " +
                  (r.track || "")).toLowerCase().indexOf(q) >= 0;
        });
      }
      function val(r, k) {
        if (k.indexOf("axes.") === 0) return r.axes[k.slice(5)];
        return r[k];
      }
      function drawDesigns() {
        var list = visible().slice();
        list.sort(function (a, b) {
          var x = val(a, sortK), y = val(b, sortK);
          if (x === null || x === undefined) return 1;
          if (y === null || y === undefined) return -1;
          if (typeof x === "string") return sortA ? x.localeCompare(y) : y.localeCompare(x);
          return sortA ? x - y : y - x;
        });
        var h = "<table><thead><tr>" +
          th("rank", "#", true) + th("design_id", "Design") + th("track", "Track") +
          th("tier", "Tier") + th("joint", "joint", true);
        axes.forEach(function (a) { h += th("axes." + a, a, true); });
        h += th("identity", "CDRH3 id", true) + th("cluster", "Cluster") +
          "</tr></thead><tbody>";
        list.forEach(function (r) {
          h += '<tr class="clickable' + (openId === r.design_id ? " open" : "") +
            '" data-id="' + esc(r.design_id) + '">' +
            '<td class="n">' + r.rank + (r.lab ? '<span class="slot">LAB</span>' : "") + "</td>" +
            "<td><code>" + esc(r.design_id) + "</code>" +
            (r.stub ? '<br><span class="stub">stub</span>' : "") + "</td>" +
            "<td>" + esc(r.track || "—") + "</td>" +
            '<td class="tier ' + esc(r.tier) + '">' + esc(r.tier) + "</td>" +
            '<td class="n">' + num(r.joint) + "</td>";
          axes.forEach(function (a) {
            var v = r.axes[a];
            h += '<td class="n">' + num(v) + bar(v) + "</td>";
          });
          h += '<td class="n">' + num(r.identity) + "</td><td>" +
            esc(r.cluster || "—") + "</td></tr>";
          if (openId === r.design_id) h += dossier(r, axes);
        });
        h += "</tbody></table>";
        document.getElementById("dtable").innerHTML = h;
        document.getElementById("dcount").textContent =
          list.length + " of " + rows.length + " shown";
        document.querySelectorAll("#dtable th[data-k]").forEach(function (t) {
          t.addEventListener("click", function () {
            if (sortK === t.dataset.k) sortA = !sortA;
            else { sortK = t.dataset.k; sortA = (sortK === "rank" || sortK === "design_id"); }
            drawDesigns();
          });
        });
        document.querySelectorAll("#dtable tr[data-id]").forEach(function (tr) {
          tr.addEventListener("click", function () {
            openId = openId === tr.dataset.id ? null : tr.dataset.id;
            drawDesigns();
          });
        });
      }
      function th(k, label, n) {
        return '<th data-k="' + k + '"' + (n ? ' class="n"' : "") + ">" + esc(label) + "</th>";
      }
      document.getElementById("dq").addEventListener("input", drawDesigns);
      document.getElementById("dlab").addEventListener("click", function () {
        labOnly = !labOnly;
        this.setAttribute("aria-pressed", labOnly ? "true" : "false");
        drawDesigns();
      });
      drawDesigns();
    }).catch(fail);
  }

  function bar(v, slow) {
    if (v === null || v === undefined) return "";
    var p = Math.max(0, Math.min(1, +v)) * 100;
    return '<div class="bar' + (v > 0.5 ? " win" : "") + '"><i style="width:' +
      p.toFixed(0) + '%"></i><u></u></div>';
  }

  function dossier(r, axes) {
    var h = '<tr><td colspan="' + (6 + axes.length) + '">';
    h += '<div class="grid">';
    axes.forEach(function (a) {
      h += "<div><div class=kv><b>" + esc(a) + "</b> · predicted</div>" +
        num(r.axes[a]) + bar(r.axes[a]) + "</div>";
    });
    h += "</div>";
    h += "<p class=kv>CDRH3 <code>" + esc(r.cdrh3 || "—") +
      "</code> · identity <b>" + num(r.identity) + "</b> · <b>" +
      (r.mutations === null ? "—" : r.mutations) + "</b> mutations · " +
      r.length + " aa · gates <b>" +
      (r.gates_passed ? "passed" : esc((r.failed_rules || []).join(", "))) + "</b></p>";
    h += "<pre>" + esc(r.sequence) + "</pre>";
    if (r.rationale && r.rationale.length) {
      h += "<p><strong>Why it is on the list</strong></p><ul>";
      r.rationale.forEach(function (x) { h += "<li>" + esc(x) + "</li>"; });
      h += "</ul>";
    }
    if (r.kill_criterion) {
      h += '<div class="note warn"><strong>Kill criterion</strong> — ' +
        esc(r.kill_criterion) + "</div>";
    }
    return h + "</td></tr>";
  }

  // ---------------------------------------------------------------- call log
  function callLog() {
    return get("/api/calls?since=0").then(function (d) {
      blink();
      state.calls = d.entries;
      state.callsTotal = d.total;
      var s = d.summary || {};
      var h = "<h1>Call log</h1>";
      if (!d.total) {
        h += '<div class="note"><h3>Nothing logged yet</h3><p>The pipeline runs ' +
          "offline against stub designs, so it makes no API calls. Every request and " +
          "response will appear here once a provider is wired in — with its " +
          "duration, and whether it was served from cache, blocked offline, or failed." +
          "</p></div>";
        view.innerHTML = h;
        return;
      }
      h += '<div class="cards">' +
        card(s.calls, "calls") + card(ms(s.total_ms), "total") +
        card(s.errors, "errors", s.errors ? "bad" : "") +
        card(s.cache_hits, "cache hits", s.cache_hits ? "good" : "") +
        card(s.offline_blocked, "offline blocked", s.offline_blocked ? "warn" : "") +
        card(ms(s.p50_ms), "p50") + card(ms(s.p95_ms), "p95") + "</div>";

      h += "<h2>Where the time goes</h2><div class=panel><table><thead><tr>" +
        '<th class="plain">Provider</th><th class="plain n">Calls</th>' +
        '<th class="plain n">Total</th><th class="plain n">Average</th>' +
        '<th class="plain n">Errors</th></tr></thead><tbody>';
      Object.keys(s.by_provider || {}).forEach(function (p) {
        var v = s.by_provider[p];
        h += "<tr><td>" + esc(p) + '</td><td class="n">' + v.calls +
          '</td><td class="n">' + ms(v.ms) + '</td><td class="n">' + ms(v.avg_ms) +
          '</td><td class="n">' + (v.errors || "") + "</td></tr>";
      });
      h += "</tbody></table></div>";

      h += "<h2>Every call</h2>";
      h += '<p class="muted">Click a row for the request and the response it returned.</p>';
      h += '<div class="controls">' +
        '<input type="search" id="lq" placeholder="Search request, response, error…">' +
        '<select id="lst"><option value="">All statuses</option></select>' +
        '<select id="lpv"><option value="">All providers</option></select>' +
        '<button class="btn" id="lslow" aria-pressed="false">Slow only</button>' +
        '<span class="muted" id="lcount"></span></div>';
      h += '<div class="panel" id="ltable"></div>';
      view.innerHTML = h;

      var statuses = {}, providers = {};
      state.calls.forEach(function (c) {
        statuses[c.status] = 1; providers[c.provider] = 1;
      });
      fill("lst", Object.keys(statuses));
      fill("lpv", Object.keys(providers));
      ["lq", "lst", "lpv"].forEach(function (id) {
        document.getElementById(id).addEventListener("input", drawCalls);
      });
      document.getElementById("lslow").addEventListener("click", function () {
        this.setAttribute("aria-pressed",
          this.getAttribute("aria-pressed") === "true" ? "false" : "true");
        drawCalls();
      });
      state.p95 = s.p95_ms;
      state.maxMs = s.max_ms || 1;
      drawCalls();
    }).catch(fail);
  }

  function fill(id, values) {
    var sel = document.getElementById(id);
    values.sort().forEach(function (v) {
      var o = document.createElement("option");
      o.value = v; o.textContent = v; sel.appendChild(o);
    });
  }

  function drawCalls() {
    var q = (document.getElementById("lq").value || "").trim().toLowerCase();
    var st = document.getElementById("lst").value;
    var pv = document.getElementById("lpv").value;
    var slow = document.getElementById("lslow").getAttribute("aria-pressed") === "true";
    var list = state.calls.filter(function (c) {
      if (st && c.status !== st) return false;
      if (pv && c.provider !== pv) return false;
      if (slow && !(c.ms >= state.p95)) return false;
      if (q) {
        var hay = (c.provider + " " + c.op + " " + (c.stage || "") + " " +
          (c.error || "") + " " + pretty(c.request) + " " + pretty(c.response)).toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    var h = "<table><thead><tr>" +
      '<th class="plain">Time</th><th class="plain">Status</th>' +
      '<th class="plain">Provider</th><th class="plain">Op</th>' +
      '<th class="plain">Stage</th><th class="plain n">Duration</th>' +
      "</tr></thead><tbody>";
    list.slice().reverse().forEach(function (c, i) {
      var idx = state.calls.indexOf(c);
      var w = Math.max(2, Math.round((c.ms / state.maxMs) * 100));
      h += '<tr class="clickable' + (state.open[idx] ? " open" : "") +
        '" data-i="' + idx + '">' +
        "<td>" + esc(c.ts) + '</td><td><span class="st ' + esc(c.status) + '">' +
        esc(c.status) + "</span></td><td>" + esc(c.provider) + "</td><td><code>" +
        esc(c.op) + "</code></td><td>" + esc(c.stage || "—") + "</td>" +
        '<td class="n">' + ms(c.ms) + '<div class="bar' +
        (c.ms >= state.p95 ? " slow" : "") + '"><i style="width:' + w +
        '%"></i></div></td></tr>';
      if (state.open[idx]) {
        h += '<tr><td colspan="6"><strong>Request</strong>' +
          (c.request_clipped ? " <em>(truncated)</em>" : "") +
          "<pre>" + esc(pretty(c.request)) + "</pre><strong>Response</strong>" +
          (c.response_clipped ? " <em>(truncated)</em>" : "") +
          "<pre>" + esc(pretty(c.response)) + "</pre>" +
          (c.error ? "<strong>Error</strong><pre>" + esc(c.error) + "</pre>" : "") +
          (c.key ? '<p class="kv">cache key <code>' + esc(c.key) + "</code></p>" : "") +
          "</td></tr>";
      }
    });
    h += "</tbody></table>";
    var box = document.getElementById("ltable");
    if (!box) return;
    box.innerHTML = list.length ? h :
      '<p class="empty">No call matches these filters.</p>';
    document.getElementById("lcount").textContent =
      list.length + " of " + state.calls.length + " calls";
    box.querySelectorAll("tr[data-i]").forEach(function (tr) {
      tr.addEventListener("click", function () {
        var i = +tr.dataset.i;
        state.open[i] = !state.open[i];
        drawCalls();
      });
    });
  }

  // ---------------------------------------------------------------- live
  function tick() {
    if (!auto.checked || !current) return;
    // Re-run the current page. Cheap: the API reads files, and the pages are
    // small. Polling beats a websocket for something that only changes when a
    // run finishes.
    current.fn(current.arg);
  }
  function startTimer() {
    if (timer) clearInterval(timer);
    timer = setInterval(tick, 4000);
  }
  auto.addEventListener("change", function () { if (auto.checked) tick(); });

  go(location.pathname, false);
  startTimer();
})();
