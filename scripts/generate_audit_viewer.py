"""Generate a dependency-free VELQIRIS evidence dashboard.

The generated page embeds a validated snapshot for file:// viewing and, when
served, refreshes from the receipt and JSONL ledger using relative URLs.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def load_receipt(path: Path) -> dict:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or "market_scenario" not in receipt:
        raise ValueError("Receipt must contain a market_scenario object")
    return receipt


def load_ledger(path: Path) -> list[dict]:
    entries: list[dict] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if not isinstance(entry, dict):
            raise ValueError(f"Ledger line {line_number} must be a JSON object")
        entries.append(entry)
    return entries


def script_safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def render_dashboard(receipt: dict, ledger: list[dict]) -> str:
    payload = script_safe_json({"receipt": receipt, "ledger": ledger})
    title = html.escape(str(receipt.get("run_id", "VELQIRIS evidence")))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VELQIRIS Audit Viewer — {title}</title>
<style>
:root{{--ink:#edf4ff;--muted:#9badc5;--panel:#101927;--line:#26384f;--cyan:#39d9ff;--mint:#62f6ba;--amber:#ffc765;--red:#ff738f;--bg:#07101c}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 80% 0,#17344a 0,transparent 38%),var(--bg);color:var(--ink);font:15px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}}
main{{max-width:1180px;margin:auto;padding:42px 22px 64px}} h1{{font:700 clamp(30px,5vw,56px)/1.03 ui-sans-serif,system-ui;margin:.15em 0}} h2{{font:700 18px ui-sans-serif,system-ui;margin:0 0 16px}} .kicker{{color:var(--cyan);letter-spacing:.18em;text-transform:uppercase}} .sub{{color:var(--muted);max-width:850px}} .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0}} .card,.panel{{background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:15px;padding:18px;box-shadow:0 18px 50px #0005}} .value{{font:700 27px ui-sans-serif,system-ui;color:var(--mint)}} .value.run-value{{font:700 13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}} .label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.12em}} .panels{{display:grid;grid-template-columns:1.2fr .8fr;gap:16px}} .row{{display:grid;grid-template-columns:130px 1fr 90px;gap:12px;align-items:center;margin:12px 0}} .track{{height:12px;background:#08111d;border-radius:20px;overflow:hidden}} .bar{{height:100%;background:linear-gradient(90deg,var(--cyan),var(--mint));border-radius:inherit}} .bar.bad{{background:linear-gradient(90deg,var(--amber),var(--red))}} .ledger{{max-height:430px;overflow:auto}} .event{{border-left:3px solid var(--cyan);padding:9px 12px;margin:9px 0;background:#09131f;border-radius:0 8px 8px 0}} code{{color:var(--cyan);word-break:break-all}} .ok{{color:var(--mint)}} .warn{{color:var(--amber)}} footer{{color:var(--muted);margin-top:22px;font-size:12px}} @media(max-width:800px){{.grid{{grid-template-columns:1fr 1fr}}.panels{{grid-template-columns:1fr}}.row{{grid-template-columns:95px 1fr 72px}}}}
</style>
</head>
<body><main>
<div class="kicker">Evidence-first / Track 02</div><h1>VELQIRIS Audit Viewer</h1>
<p class="sub" id="boundary"></p>
<section class="grid" id="metrics"></section>
<section class="panels"><div class="panel"><h2>Venue telemetry &amp; consensus</h2><div id="venues"></div></div><div class="panel"><h2>Append-only trust ledger</h2><div class="ledger" id="ledger"></div></div></section>
<footer>Standalone snapshot generated from <code>evidence/zetaris-live-receipt.json</code> and <code>evidence/meterless-hmem-runtime/ledger.jsonl</code>. When hosted, the viewer attempts a same-origin refresh from those files. No external JavaScript or analytics.</footer>
</main><script>
const embedded={payload};
const text=(v)=>v===undefined||v===null?'—':String(v);
function draw(data){{
 const r=data.receipt, s=r.market_scenario||{{}}, q=s.query_result||{{}}, c=s.velqiris_mad_consensus||{{}}, rows=q.rows||[], events=data.ledger||[];
 document.getElementById('boundary').textContent=s.claim_boundary||'Evidence scope unavailable.';
 const cards=[['Run',r.run_id],['Zetaris rows',q.row_count],['Ledger events',events.length],['Risk regime',c.risk_regime]];
 document.getElementById('metrics').replaceChildren(...cards.map(([k,v])=>{{const d=document.createElement('div');d.className='card';const x=document.createElement('div');x.className='value'+(k==='Run'?' run-value':'');x.textContent=text(v);const l=document.createElement('div');l.className='label';l.textContent=k;d.append(x,l);return d;}}));
 const maxLatency=Math.max(1,...rows.map(x=>Number(x.latency_ms)||0)); const rejected=new Set((c.rejected_outliers||[]).map(x=>x.venue));
 document.getElementById('venues').replaceChildren(...rows.map(x=>{{const d=document.createElement('div');d.className='row';const n=document.createElement('div');n.textContent=text(x.venue);const t=document.createElement('div');t.className='track';const b=document.createElement('div');b.className='bar'+(rejected.has(x.venue)?' bad':'');b.style.width=Math.max(3,(Number(x.latency_ms)||0)/maxLatency*100)+'%';t.append(b);const v=document.createElement('div');v.className=rejected.has(x.venue)?'warn':'ok';v.textContent=text(x.latency_ms)+' ms';d.append(n,t,v);return d;}}));
 document.getElementById('ledger').replaceChildren(...events.map((x,i)=>{{const d=document.createElement('div');d.className='event';d.textContent=(i+1)+'. '+text(x.action)+' · '+text(x.memoryId||x.memory_id||x.id);return d;}}));
}}
draw(embedded);
Promise.all([fetch('../evidence/zetaris-live-receipt.json').then(r=>r.ok?r.json():Promise.reject()),fetch('../evidence/meterless-hmem-runtime/ledger.jsonl').then(r=>r.ok?r.text():Promise.reject())]).then(([receipt,raw])=>draw({{receipt,ledger:raw.split(/\\n/).filter(Boolean).map(JSON.parse)}})).catch(()=>{{}});
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    page = render_dashboard(load_receipt(args.receipt), load_ledger(args.ledger))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"Audit viewer written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
