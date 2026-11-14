"""The log UI — every call, its request and response, and where the time went.

Two ways to look at the same log, both local, both stdlib:

    python3 -m fourwells.logview              # write logs/index.html and stop
    python3 -m fourwells.logview --serve      # watch it live on localhost

`--serve` runs a loopback-only HTTP server that re-reads the log on every
request and auto-refreshes, which is what you want while a run is going. It
binds 127.0.0.1 deliberately: the log holds request and response bodies, and
nothing here should be reachable from the conference network.

The static file is the same page with the data frozen in, so it still opens
from a file:// URL after the machine it ran on is gone.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from .calllog import DEFAULT_LOG, read_log, summarise

STATUS_ORDER = ["ok", "cache_hit", "offline_blocked", "error"]

_CSS = """
:root{--ink:#16181d;--mut:#5c6370;--line:#e3e6ea;--bg:#fff;--card:#fff;--acc:#1f6feb;
--good:#107c41;--bad:#b42318;--warn:#8a5a00;--chip:#f4f6f8;--hi:#eaf2ff}
@media(prefers-color-scheme:dark){:root{--ink:#e6e9ef;--mut:#9aa3b2;--line:#2b3038;
--bg:#14161a;--card:#191c21;--acc:#6ea8fe;--good:#4ec97f;--bad:#ff7b72;--warn:#e3b341;
--chip:#1d2026;--hi:#1b2433}}
*{box-sizing:border-box}
body{margin:0;padding:1.75rem 1.25rem 4rem;background:var(--bg);color:var(--ink);
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:78rem;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 .2rem;letter-spacing:-.02em}
h2{font-size:1.1rem;margin:2rem 0 .6rem;padding-bottom:.3rem;border-bottom:1px solid var(--line)}
p{margin:.35rem 0}
.sub{color:var(--mut);font-size:13px;margin:0 0 1.25rem}
code,pre{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre{background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:.6rem .8rem;
overflow-x:auto;margin:.35rem 0;max-height:22rem;white-space:pre-wrap;word-break:break-word}
.stats{display:flex;flex-wrap:wrap;gap:.6rem;margin:1rem 0}
.stat{flex:1 1 7.5rem;border:1px solid var(--line);border-radius:8px;padding:.55rem .8rem;
background:var(--card)}
.stat b{display:block;font-size:1.3rem;line-height:1.2;font-variant-numeric:tabular-nums}
.stat span{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.stat.bad b{color:var(--bad)}.stat.good b{color:var(--good)}.stat.warn b{color:var(--warn)}
table{border-collapse:collapse;width:100%;font-size:13px;margin:.5rem 0}
th,td{text-align:left;padding:.35rem .55rem;border-bottom:1px solid var(--line);
vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);
font-weight:600;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.controls{display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;margin:.6rem 0}
.controls input,.controls select{font:inherit;font-size:13px;padding:.3rem .45rem;
border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
.controls input[type=search]{flex:1 1 14rem}
.btn{font:inherit;font-size:13px;padding:.3rem .6rem;border:1px solid var(--line);
border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
.btn:hover{background:var(--hi)}
.btn[aria-pressed=true]{border-color:var(--acc);color:var(--acc)}
.st{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.04em;
padding:.1em .45em;border-radius:3px;text-transform:uppercase;border:1px solid}
.st.ok{color:var(--good);border-color:var(--good)}
.st.cache_hit{color:var(--acc);border-color:var(--acc)}
.st.offline_blocked{color:var(--warn);border-color:var(--warn)}
.st.error{color:var(--bad);border-color:var(--bad)}
#rows tr.r{cursor:pointer}
#rows tr.r:hover{background:var(--hi)}
#rows tr.d td{background:var(--chip)}
.lat{position:relative;height:5px;background:var(--line);border-radius:3px;min-width:3rem;
margin-top:.25rem}
.lat i{position:absolute;top:0;bottom:0;left:0;background:var(--acc);border-radius:3px}
.lat.slow i{background:var(--warn)}
.none{color:var(--mut);font-style:italic;padding:1rem 0}
.live{display:inline-block;width:.5rem;height:.5rem;border-radius:50%;background:var(--good);
margin-right:.35rem}
footer{max-width:78rem;margin:2.5rem auto 0;padding-top:.8rem;border-top:1px solid var(--line);
color:var(--mut);font-size:12px}
"""

_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('data').textContent);
var rows=D.entries, open=new Set(), sortK='i', sortA=false;
function esc(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML}
function pretty(v){
  if(v==null) return '(none)';
  if(typeof v==='string') return v;
  try{return JSON.stringify(v,null,2)}catch(e){return String(v)}
}
function visible(){
  var q=document.getElementById('q').value.trim().toLowerCase();
  var st=document.getElementById('fst').value, pv=document.getElementById('fpv').value;
  var rn=document.getElementById('frun').value;
  var slow=document.getElementById('fslow').getAttribute('aria-pressed')==='true';
  return rows.filter(function(r){
    if(st&&r.status!==st) return false;
    if(pv&&r.provider!==pv) return false;
    if(rn&&r.run_id!==rn) return false;
    if(slow&&!(r.ms>=D.p95)) return false;
    if(q){
      var hay=(r.provider+' '+r.op+' '+(r.stage||'')+' '+(r.error||'')+' '
        +pretty(r.request)+' '+pretty(r.response)).toLowerCase();
      if(hay.indexOf(q)<0) return false;
    }
    return true;
  });
}
function draw(){
  var list=visible().slice();
  list.sort(function(a,b){
    var x=a[sortK],y=b[sortK];
    if(x==null)return 1; if(y==null)return -1;
    if(typeof x==='string') return sortA?x.localeCompare(y):y.localeCompare(x);
    return sortA?x-y:y-x;
  });
  var h='', max=D.maxMs||1;
  list.forEach(function(r){
    var w=Math.max(2,Math.round((r.ms/max)*100));
    h+='<tr class="r" data-i="'+r.i+'">'
      +'<td>'+esc(r.ts)+'</td>'
      +'<td><span class="st '+esc(r.status)+'">'+esc(r.status)+'</span></td>'
      +'<td>'+esc(r.provider)+'</td><td><code>'+esc(r.op)+'</code></td>'
      +'<td>'+esc(r.stage||'—')+'</td>'
      +'<td class="n">'+r.ms.toFixed(1)+' ms<div class="lat'+(r.ms>=D.p95?' slow':'')
      +'"><i style="width:'+w+'%"></i></div></td>'
      +'<td>'+esc(r.run_id||'—')+'</td></tr>';
    if(open.has(r.i)){
      h+='<tr class="d"><td colspan="7">'
        +'<strong>Request</strong>'+(r.request_clipped?' <em>(truncated)</em>':'')
        +'<pre>'+esc(pretty(r.request))+'</pre>'
        +'<strong>Response</strong>'+(r.response_clipped?' <em>(truncated)</em>':'')
        +'<pre>'+esc(pretty(r.response))+'</pre>'
        +(r.error?'<strong>Error</strong><pre>'+esc(r.error)+'</pre>':'')
        +(r.key?'<p class="sub">cache key <code>'+esc(r.key)+'</code></p>':'')
        +'</td></tr>';
    }
  });
  document.getElementById('rows').innerHTML=h ||
    '<tr><td colspan="7" class="none">No call matches these filters.</td></tr>';
  document.getElementById('count').textContent=list.length+' of '+rows.length+' calls'
    +(list.length?' · '+list.reduce(function(a,r){return a+r.ms},0).toFixed(0)+' ms total':'');
}
document.getElementById('rows').addEventListener('click',function(e){
  var tr=e.target.closest('tr.r'); if(!tr) return;
  var i=+tr.dataset.i;
  if(open.has(i)) open.delete(i); else open.add(i);
  draw();
});
document.querySelectorAll('#tbl th[data-k]').forEach(function(th){
  th.addEventListener('click',function(){
    if(sortK===th.dataset.k) sortA=!sortA; else {sortK=th.dataset.k; sortA=false;}
    draw();
  });
});
['q','fst','fpv','frun'].forEach(function(id){
  document.getElementById(id).addEventListener('input',draw);
});
document.getElementById('fslow').addEventListener('click',function(){
  this.setAttribute('aria-pressed',this.getAttribute('aria-pressed')==='true'?'false':'true');
  draw();
});
document.getElementById('expand').addEventListener('click',function(){
  if(open.size){open.clear()} else {visible().forEach(function(r){open.add(r.i)})}
  draw();
});
draw();
})();
"""


def _h(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _payload(entries: list[dict], summary: dict) -> str:
    rows = []
    for i, e in enumerate(entries):
        rows.append({
            "i": i,
            "ts": e.get("ts", ""),
            "status": e.get("status", "?"),
            "provider": e.get("provider", "?"),
            "op": e.get("op", ""),
            "stage": e.get("stage", ""),
            "ms": float(e.get("ms", 0) or 0),
            "run_id": e.get("run_id", ""),
            "request": e.get("request"),
            "response": e.get("response"),
            "request_clipped": bool(e.get("request_clipped")),
            "response_clipped": bool(e.get("response_clipped")),
            "error": e.get("error"),
            "key": e.get("key"),
        })
    blob = {
        "entries": rows,
        "p95": summary.get("p95_ms", 0),
        "maxMs": summary.get("max_ms", 1) or 1,
    }
    return json.dumps(blob, default=str, separators=(",", ":")).replace("<", "\\u003c")


def render(entries: list[dict], log_path: Path, live: bool = False,
           refresh: int = 3) -> str:
    s = summarise(entries)
    providers = sorted({e.get("provider", "?") for e in entries})
    runs = sorted({e.get("run_id", "") for e in entries if e.get("run_id")}, reverse=True)
    statuses = [x for x in STATUS_ORDER if x in s["by_status"]]

    H: list[str] = []
    A = H.append
    A("<!DOCTYPE html>")
    A('<html lang="en"><head><meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width,initial-scale=1">')
    if live:
        A(f'<meta http-equiv="refresh" content="{refresh}">')
    A("<title>FourWells — call log</title>")
    A(f"<style>{_CSS}</style></head><body><main>")

    A("<h1>Call log</h1>")
    A(f'<p class="sub">'
      + ('<span class="live"></span>live, refreshing every %ds · ' % refresh if live else "")
      + f"{s['calls']} calls from <code>{_h(log_path)}</code>"
      + (f" · {len(runs)} run(s)" if runs else "") + "</p>")

    if not entries:
        A('<p class="none">The log is empty. Run the pipeline '
          "(<code>make demo</code>) and this fills up.</p>")
        A("</main></body></html>")
        return "\n".join(H) + "\n"

    # --- headline numbers ---
    A('<div class="stats">')
    err_cls = " bad" if s["errors"] else ""
    blocked_cls = " warn" if s["offline_blocked"] else ""
    for val, label, cls in (
        (s["calls"], "calls", ""),
        (f"{s['total_ms'] / 1000:.1f} s", "total time", ""),
        (s["errors"], "errors", err_cls),
        (f"{100 * s['error_rate']:.0f}%", "error rate", err_cls),
        (s["cache_hits"], "cache hits", " good" if s["cache_hits"] else ""),
        (s["offline_blocked"], "offline blocked", blocked_cls),
        (f"{s['p50_ms']:.0f} ms", "p50", ""),
        (f"{s['p95_ms']:.0f} ms", "p95", ""),
        (f"{s['max_ms']:.0f} ms", "slowest", ""),
    ):
        A(f'<div class="stat{cls}"><b>{_h(val)}</b><span>{_h(label)}</span></div>')
    A("</div>")

    if s["offline_blocked"]:
        A(f'<p class="sub">{s["offline_blocked"]} call(s) were blocked by offline mode — '
          "the cache had no value and <code>compute()</code> was never run. That is the "
          "default and usually correct, but it is also the reason a run can finish "
          "quickly and produce nothing.</p>")

    # --- where the time goes ---
    A("<h2>Where the time goes</h2>")
    A('<table><thead><tr><th>Provider</th><th class="n">Calls</th>'
      '<th class="n">Total</th><th class="n">Average</th><th class="n">Slowest</th>'
      '<th class="n">Errors</th></tr></thead><tbody>')
    for name, p in s["by_provider"].items():
        share = p["ms"] / s["total_ms"] if s["total_ms"] else 0
        A(f'<tr><td>{_h(name)}<div class="lat"><i style="width:'
          f'{100 * share:.0f}%"></i></div></td>'
          f'<td class="n">{p["calls"]}</td>'
          f'<td class="n">{p["ms"] / 1000:.2f} s</td>'
          f'<td class="n">{p["avg_ms"]:.0f} ms</td>'
          f'<td class="n">{p["slowest"]:.0f} ms<br><code>{_h(p["slowest_op"])}</code></td>'
          f'<td class="n">{p["errors"] or ""}</td></tr>')
    A("</tbody></table>")

    if len(s["by_run"]) > 1:
        A("<h2>By run</h2>")
        A('<table><thead><tr><th>Run</th><th>Started</th><th class="n">Calls</th>'
          '<th class="n">Time</th><th class="n">Errors</th></tr></thead><tbody>')
        for name, r in sorted(s["by_run"].items(), reverse=True):
            A(f'<tr><td><code>{_h(name)}</code></td><td>{_h(r["first"])}</td>'
              f'<td class="n">{r["calls"]}</td><td class="n">{r["ms"] / 1000:.2f} s</td>'
              f'<td class="n">{r["errors"] or ""}</td></tr>')
        A("</tbody></table>")

    # --- the log itself ---
    A("<h2>Every call</h2>")
    A('<p class="sub">Click a row to see the request and the response it got back.</p>')
    A('<div class="controls">')
    A('<input type="search" id="q" placeholder="Search request, response, error…" '
      'aria-label="Search the log">')
    A('<select id="fst" aria-label="Filter by status"><option value="">All statuses</option>'
      + "".join(f'<option value="{_h(x)}">{_h(x)}</option>' for x in statuses) + "</select>")
    A('<select id="fpv" aria-label="Filter by provider">'
      '<option value="">All providers</option>'
      + "".join(f'<option value="{_h(x)}">{_h(x)}</option>' for x in providers) + "</select>")
    A('<select id="frun" aria-label="Filter by run"><option value="">All runs</option>'
      + "".join(f'<option value="{_h(x)}">{_h(x)}</option>' for x in runs) + "</select>")
    A(f'<button class="btn" id="fslow" aria-pressed="false">Slow only '
      f'(≥ p95, {s["p95_ms"]:.0f} ms)</button>')
    A('<button class="btn" id="expand">Expand / collapse all</button>')
    A('<span class="sub" id="count"></span>')
    A("</div>")
    A('<table id="tbl"><thead><tr>'
      '<th data-k="ts">Time</th><th data-k="status">Status</th>'
      '<th data-k="provider">Provider</th><th data-k="op">Op</th>'
      '<th data-k="stage">Stage</th><th class="n" data-k="ms">Duration</th>'
      '<th data-k="run_id">Run</th></tr></thead><tbody id="rows"></tbody></table>')

    A("</main><footer>")
    A("Local only. Request and response bodies are truncated and anything that looks "
      "like a credential is redacted before writing, but this file still holds what we "
      "sent and what came back — keep it off the public repo.")
    A("</footer>")
    A(f'<script type="application/json" id="data">{_payload(entries, s)}</script>')
    A(f"<script>{_JS}</script>")
    A("</body></html>")
    return "\n".join(H) + "\n"


PORT_SPAN = 20  # how far forward to look when the requested port is taken


def bind(host: str, port: int, handler):
    """First free port at or after `port`. Returns (server, port) or (None, port).

    Split out of `serve` so the fallback is testable without starting a thread
    and racing it — which is exactly how the first version of its test failed.
    """
    from http.server import ThreadingHTTPServer

    for candidate in range(port, port + PORT_SPAN):
        try:
            return ThreadingHTTPServer((host, candidate), handler), candidate
        except OSError:
            continue
    return None, port


def serve(log_path: Path, host: str = "127.0.0.1", port: int = 8765,
          refresh: int = 3, open_browser: bool = True) -> None:
    """Live view on loopback. Re-reads the log on every request.

    Threaded, because a browser holds connections open and a single-threaded
    server can sit there looking alive while the page never loads. Any path
    serves the page rather than 404-ing, so a mistyped URL still works, and if
    the port is taken we move to the next free one and say so instead of dying
    on "address already in use".
    """
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive; browsers expect it

        def do_GET(self):  # noqa: N802
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                body = render(read_log(log_path), log_path, live=True,
                              refresh=refresh).encode()
                code = 200
            except Exception as exc:  # noqa: BLE001 — show the error, don't hang
                body = (f"<!DOCTYPE html><meta charset=utf-8>"
                        f"<title>call log error</title>"
                        f"<pre>{html.escape(repr(exc))}</pre>").encode()
                code = 500
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # quiet; the page is the output
            pass

    srv, port = bind(host, port, Handler)
    if srv is None:
        print(f"could not bind any port in {port}..{port + PORT_SPAN - 1} on {host}.")
        print("Something else is using them. Pass --port to pick another.")
        return

    url = f"http://{host}:{port}/"
    print(f"\n  call log  {url}")
    print(f"  reading   {log_path}")
    print(f"  refresh   every {refresh}s · Ctrl-C to stop\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 — a headless box has no browser
            print("  (could not open a browser automatically — open the URL above)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fourwells.logview",
        description="Browse the call log: requests, responses, timings",
    )
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--out", type=Path, default=None,
                    help="where to write the static page (default: next to the log)")
    ap.add_argument("--serve", action="store_true", help="live view on localhost")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--refresh", type=int, default=3, help="live refresh seconds")
    ap.add_argument("--no-open", action="store_true",
                    help="do not open a browser automatically")
    a = ap.parse_args(argv)

    if a.serve:
        serve(a.log, port=a.port, refresh=a.refresh, open_browser=not a.no_open)
        return 0

    entries = read_log(a.log)
    out = a.out or a.log.parent / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(entries, a.log))
    print(f"wrote {out} ({len(entries)} calls)")
    if not entries:
        print("the log is empty — run `make demo` first")
    # Print the file:// URL and open it. A bare path is not clickable in every
    # terminal, and "it wrote a file somewhere" is not a UI.
    print(f"  {out.resolve().as_uri()}")
    if not a.no_open:
        import webbrowser

        try:
            webbrowser.open(out.resolve().as_uri())
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
