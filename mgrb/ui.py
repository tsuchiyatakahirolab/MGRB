from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .importer import SUPPORTED_SUFFIXES, inspect_input, normalize_user_input
from .product import ProductBuildSpec, product_catalog, safe_build_id
from .workflow import execute_product_build

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


@dataclass
class UIState:
    root: Path
    output_root: Path
    upload_root: Path
    uploads: dict[str, Path] = field(default_factory=dict)


def _safe_filename(value: str) -> str:
    name = Path(unquote(value)).name
    if not name or name in {".", ".."}:
        raise ValueError("Missing upload filename")
    if Path(name).suffix.casefold() not in SUPPORTED_SUFFIXES:
        raise ValueError("Use CSV, GeoJSON, GeoPackage, or Shapefile")
    return name


class MGRBUIHandler(BaseHTTPRequestHandler):
    server_version = "MGRBLocalUI/1.0"
    state: UIState

    def log_message(self, fmt: str, *args) -> None:
        print(f"MGRB UI {self.address_string()} {fmt % args}")

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES:
            raise ValueError("Upload exceeds the 1 GiB local UI limit")
        return self.rfile.read(length)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = UI_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/catalog":
            self._json(product_catalog(self.state.root))
            return
        if path == "/api/health":
            self._json({"ok": True, "service": "mgrb-ui", "bind": "loopback-only"})
            return
        if path.startswith("/outputs/"):
            target = (self.state.output_root / path.removeprefix("/outputs/")).resolve()
            if not target.is_relative_to(self.state.output_root.resolve()) or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            if path == "/api/inspect":
                filename = _safe_filename(self.headers.get("X-MGRB-Filename", ""))
                token = uuid.uuid4().hex
                target = self.state.upload_root / token / filename
                target.parent.mkdir(parents=True, exist_ok=False)
                target.write_bytes(self._body())
                inspection = inspect_input(target)
                self.state.uploads[token] = target
                qc_summary = None
                if not inspection.requires_confirmation:
                    _, qc_summary = normalize_user_input(
                        target, build_id=f"ui-inspect-{token[:12]}"
                    )
                self._json(
                    {
                        "ok": True,
                        "token": token,
                        "inspection": inspection.to_dict(),
                        "qc_summary": qc_summary,
                    }
                )
                return
            if path == "/api/qc":
                payload = json.loads(self._body() or b"{}")
                token = str(payload.get("token") or "")
                if token not in self.state.uploads:
                    raise ValueError(f"Unknown or expired upload token: {token}")
                _, summary = normalize_user_input(
                    self.state.uploads[token],
                    build_id=f"ui-inspect-{token[:12]}",
                    field_map=dict(payload.get("field_map") or {}),
                )
                self._json({"ok": True, "qc_summary": summary})
                return
            if path == "/api/preview":
                payload = json.loads(self._body() or b"{}")
                spec, inspections = self._resolve_spec(payload)
                spec.validate(self.state.root)
                catalog = product_catalog(self.state.root)
                area = next(item for item in catalog["areas"] if item["id"] == spec.area)
                self._json(
                    {
                        "ok": True,
                        "area": area,
                        "background": spec.background,
                        "maritime_layers": list(spec.maritime_layers),
                        "inputs": inspections,
                        "notice": (
                            "Selection preview only. Publication outputs use canonical "
                            "headless QGIS rendering."
                        ),
                    }
                )
                return
            if path == "/api/build":
                payload = json.loads(self._body() or b"{}")
                spec, _ = self._resolve_spec(payload)
                build_id = safe_build_id(
                    str(payload.get("build_id") or self._default_build_id(spec.area))
                )
                result, archive = execute_product_build(
                    spec,
                    output_root=self.state.output_root,
                    repository_root=self.state.root,
                    build_id=build_id,
                )
                self._json(
                    {
                        "ok": True,
                        "build_id": result.build_id,
                        "package": str(result.output),
                        "qgis_project": str(result.qgis_project),
                        "archive": str(archive),
                        "elapsed_seconds": round(result.elapsed_seconds, 3),
                    }
                )
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - HTTP boundary returns a fail-closed error
            self._json(
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )

    def _resolve_spec(self, payload: dict) -> tuple[ProductBuildSpec, list[dict]]:
        tokens = [str(value) for value in payload.pop("upload_tokens", ())]
        paths = []
        inspections = []
        field_maps: dict[str, dict[str, str]] = {}
        requested_maps = payload.get("field_maps") or {}
        requested_kinds = payload.pop("input_kinds", {}) or {}
        requested_metadata = payload.pop("input_metadata", {}) or {}
        input_kinds: dict[str, str] = {}
        input_metadata: dict[str, dict[str, str]] = {}
        for token in tokens:
            if token not in self.state.uploads:
                raise ValueError(f"Unknown or expired upload token: {token}")
            path = self.state.uploads[token]
            paths.append(str(path))
            inspections.append(inspect_input(path).to_dict())
            if token in requested_maps:
                field_maps[str(path)] = dict(requested_maps[token])
            input_kinds[str(path)] = str(requested_kinds.get(token) or "TRACK")
            if token in requested_metadata:
                input_metadata[str(path)] = dict(requested_metadata[token])
        payload["input_files"] = paths
        payload["field_maps"] = field_maps
        payload["input_kinds"] = input_kinds
        payload["input_metadata"] = input_metadata
        return ProductBuildSpec.from_dict(payload), inspections

    @staticmethod
    def _default_build_id(area: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"MGRB-{area}-{timestamp}"


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    root: Path = ROOT,
    output_root: Path | None = None,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("MGRB UI is local-only; bind to a loopback address")
    state = UIState(
        root=root.resolve(),
        output_root=(output_root or root / "build" / "products").resolve(),
        upload_root=(root / ".tmp" / "mgrb-ui" / "uploads").resolve(),
    )
    state.output_root.mkdir(parents=True, exist_ok=True)
    state.upload_root.mkdir(parents=True, exist_ok=True)
    handler = type("BoundMGRBUIHandler", (MGRBUIHandler,), {"state": state})
    return ThreadingHTTPServer((host, port), handler)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    output_root: Path | None = None,
) -> None:
    server = create_server(host=host, port=port, output_root=output_root)
    url = f"http://{host}:{server.server_address[1]}/"
    print(json.dumps({"ok": True, "url": url, "bind": "loopback-only"}, indent=2))
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="mgrb ui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    serve(
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
        output_root=args.output_root,
    )


UI_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MGRB — Maritime Research Workspace Builder</title>
<style>
:root{--ink:#12252c;--muted:#60727a;--paper:#f5f2eb;--panel:#fffdf7;--sea:#d9e7e8;
--accent:#b84935;--line:#ced8d7;--good:#246b54;--shadow:0 18px 46px rgba(15,43,51,.11)}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:"Segoe UI",Arial,sans-serif}header{height:72px;padding:0 5vw;display:flex;
align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);
background:rgba(255,253,247,.9)}.brand{font:700 22px Georgia,serif;letter-spacing:.08em}
.brand small{font:500 11px "Segoe UI";color:var(--muted);display:block;letter-spacing:.16em}
.status{font-size:12px;color:var(--good)}main{max-width:1480px;margin:0 auto;padding:28px 4vw 48px;
display:grid;grid-template-columns:minmax(360px,480px) minmax(480px,1fr);gap:24px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}
.controls{padding:24px}.eyebrow{font-size:10px;letter-spacing:.18em;color:var(--accent);
font-weight:800}.lead{font:600 25px/1.15 Georgia,serif;margin:7px 0 20px}.step{padding:17px 0;
border-top:1px solid #e5e6df}.step:first-of-type{border-top:0}.step h2{font-size:12px;
letter-spacing:.12em;margin:0 0 9px}.step h2 span{color:var(--accent);margin-right:7px}
select,input[type=text],input[type=date]{width:100%;padding:11px 12px;border:1px solid #bbc9c8;
border-radius:8px;background:white;color:var(--ink);font:inherit}.check-grid{display:grid;
grid-template-columns:1fr 1fr;gap:7px}.check{display:flex;gap:8px;align-items:flex-start;
font-size:13px;padding:7px;border-radius:7px}.check:hover{background:#f1f4ef}
.drop{border:1.5px dashed #8ca3a5;border-radius:12px;padding:20px;text-align:center;
background:#f7faf7;transition:.2s}.drop.over{border-color:var(--accent);background:#fbebe6}
.drop strong{display:block;margin-bottom:5px}.drop small{color:var(--muted)}button{border:0;
border-radius:9px;padding:11px 16px;font-weight:700;cursor:pointer}.secondary{background:#e8eeee;
color:var(--ink);margin-top:10px}.build{width:100%;background:var(--accent);color:white;
font-size:15px;padding:14px;margin-top:16px}.build:disabled{opacity:.45}.file-card{margin-top:10px;
padding:11px;border:1px solid var(--line);border-radius:9px;background:#fff}.file-card b{font-size:13px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}.metric{background:#f1f4ef;
padding:7px;border-radius:6px}.metric strong{display:block;font-size:15px}.metric small{color:var(--muted)}
.warning{color:#9e3e2c;font-size:12px;margin-top:7px}.right{display:grid;grid-template-rows:auto auto;
gap:18px}.map-panel{overflow:hidden}.map-head{padding:17px 20px;display:flex;align-items:center;
justify-content:space-between;border-bottom:1px solid var(--line)}.map-head h2{font:600 17px Georgia;
margin:0}.map-head span{font-size:11px;color:var(--muted)}#preview{height:570px;position:relative;
background:linear-gradient(145deg,#e9f0ee,#c9dddf);overflow:hidden}.graticule{position:absolute;
inset:0;background-image:linear-gradient(rgba(43,74,82,.12) 1px,transparent 1px),
linear-gradient(90deg,rgba(43,74,82,.12) 1px,transparent 1px);background-size:12.5% 16.666%}
#trackSvg{position:absolute;inset:0;width:100%;height:100%}.map-label{position:absolute;left:24px;
top:22px;background:rgba(255,253,247,.9);padding:10px 12px;border-left:3px solid var(--accent)}
.map-label b{font:600 18px Georgia;display:block}.map-label small{color:var(--muted)}
.layer-chips{position:absolute;right:16px;bottom:16px;max-width:52%;display:flex;
justify-content:flex-end;flex-wrap:wrap;gap:5px}.chip{background:rgba(18,37,44,.86);color:white;
padding:5px 8px;border-radius:12px;font-size:10px}.notice{padding:14px 20px;font-size:12px;
color:var(--muted);border-top:1px solid var(--line)}.result{padding:18px 20px;min-height:82px}
.result h3{margin:0 0 7px;font:600 15px Georgia}.result pre{white-space:pre-wrap;font-size:11px;
background:#17292f;color:#e9f3ef;border-radius:8px;padding:12px;max-height:220px;overflow:auto}
.hidden{display:none}@media(max-width:960px){main{grid-template-columns:1fr}#preview{height:440px}}
details{margin-top:8px;border:1px solid var(--line);border-radius:9px;padding:8px}
summary{cursor:pointer;font-size:12px;font-weight:700}.source-note{display:block;color:var(--muted);
font-size:10px;margin-top:2px}.date-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
</style>
</head>
<body>
<header><div class="brand">MGRB<small>MARITIME GEOSPATIAL RESEARCH BASE</small></div>
<div class="status">● LOCAL · PRIVATE INPUTS STAY ON THIS COMPUTER</div></header>
<main>
<section class="panel controls">
<div class="eyebrow">RESEARCH WORKSPACE BUILDER</div>
<div class="lead">Make the research choice.<br>MGRB handles the GIS setup.</div>
<div class="step"><h2><span>01</span>AREA</h2><select id="area"></select>
<div id="customBox" class="hidden"><input id="customExtent" type="text"
placeholder="west, south, east, north"></div></div>
<div class="step"><h2><span>02</span>BACKGROUND</h2><select id="background"></select></div>
<div class="step"><h2><span>03</span>MARITIME LAYERS</h2>
<div id="layers" class="check-grid"></div>
<details><summary>Context and evidence layers</summary><div id="contextLayers"></div></details></div>
<div class="step"><h2><span>04</span>VESSEL / USER DATA</h2>
<div id="drop" class="drop"><strong>Drop CSV / GeoJSON / GeoPackage here</strong>
<small>or choose a local file · nothing is uploaded to a cloud service</small><br>
<button class="secondary" id="choose">Choose file</button>
<input id="file" class="hidden" type="file" accept=".csv,.tsv,.geojson,.json,.gpkg,.shp"></div>
<div id="files"></div></div>
<div class="step"><h2><span>05</span>TIME FILTER</h2><div class="date-grid">
<label>Start date<input id="startDate" type="date"></label>
<label>End date<input id="endDate" type="date"></label></div></div>
<div class="step"><h2><span>06</span>OUTPUT</h2><div id="outputs" class="check-grid"></div></div>
<button class="build" id="build">BUILD RESEARCH PACKAGE</button>
</section>
<section class="right">
<div class="panel map-panel"><div class="map-head"><h2>Interactive selection preview</h2>
<span id="profile">CANONICAL QGIS OUTPUT</span></div><div id="preview"><div class="graticule"></div>
<svg id="trackSvg"></svg>
<div class="map-label"><b id="areaLabel">Taiwan East</b><small id="areaPurpose"></small></div>
<div id="chips" class="layer-chips"></div></div><div class="notice">This preview is for extent,
layer-state and data inspection. Paper, media and QGIS outputs use the accepted canonical QGIS pipeline.</div></div>
<div class="panel result"><h3>Build / validation status</h3><div id="message">Ready.</div>
<pre id="details" class="hidden"></pre></div>
</section>
</main>
<script>
const state={catalog:null,uploads:[],fieldMaps:{},inputKinds:{},inputMetadata:{}};
const $=id=>document.getElementById(id);
async function init(){state.catalog=await (await fetch('/api/catalog')).json();
fillSelect('area',state.catalog.areas);fillSelect('background',state.catalog.backgrounds);
state.catalog.maritime_layers.forEach(x=>$('layers').append(check(x.id,x.label,
state.catalog.defaults.maritime_layers.includes(x.id),'layer')));
Object.entries(state.catalog.context_layer_groups).forEach(([group,items])=>{const details=
document.createElement('details');const summary=document.createElement('summary');summary.textContent=
group.replaceAll('_',' ');details.append(summary);items.filter(x=>x.source_class!=='REFERENCE_ONLY')
.forEach(x=>{const item=check(x.layer_id,x.dataset,Boolean(x.default_enabled),'context');
item.title=x.provider+' · '+x.license+' · '+x.attribution;const note=document.createElement('span');
note.className='source-note';note.textContent=x.provider+' · '+x.license;item.append(note);details.append(item)});
$('contextLayers').append(details)});
state.catalog.outputs.forEach(x=>$('outputs').append(check(x,x==='qgis'?'QGIS Research Package':
x[0].toUpperCase()+x.slice(1),true,'output')));bind();updatePreview()}
function fillSelect(id,items){items.forEach(x=>{const o=document.createElement('option');o.value=x.id;
o.textContent=x.label;$(id).append(o)})}
function check(id,label,on,kind){const l=document.createElement('label');l.className='check';
const i=document.createElement('input');i.type='checkbox';i.value=id;i.checked=on;i.dataset.kind=kind;
i.addEventListener('change',updatePreview);l.append(i,document.createTextNode(label));return l}
function bind(){$('choose').onclick=e=>{e.preventDefault();$('file').click()};
$('file').onchange=e=>inspectFiles(e.target.files);['dragenter','dragover'].forEach(n=>$('drop')
.addEventListener(n,e=>{e.preventDefault();$('drop').classList.add('over')}));
['dragleave','drop'].forEach(n=>$('drop').addEventListener(n,e=>{e.preventDefault();
$('drop').classList.remove('over')}));$('drop').addEventListener('drop',e=>inspectFiles(e.dataTransfer.files));
$('area').onchange=()=>{$('customBox').classList.toggle('hidden',$('area').value!=='custom');
updatePreview()};$('background').onchange=updatePreview;$('build').onclick=build}
async function inspectFiles(files){for(const file of files){$('message').textContent='Inspecting '+file.name+'…';
const r=await fetch('/api/inspect',{method:'POST',headers:{'X-MGRB-Filename':file.name},body:file});
const data=await r.json();if(!data.ok){showError(data);return}state.uploads.push(data);
renderFile(data);updatePreview()}$('message').textContent='Input inspection complete.'}
function renderFile(data){const x=data.inspection,d=document.createElement('div');d.className='file-card';
d.innerHTML='<b></b><div class="metrics"><div class="metric"><strong>'+Number(x.record_count)+
'</strong><small>records</small></div><div class="metric"><strong></strong><small>format</small></div>'+
'<div class="metric"><strong></strong><small>schema</small></div></div>';d.querySelector('b').textContent=
x.filename;const strong=d.querySelectorAll('.metric strong');strong[1].textContent=x.format.toUpperCase();
strong[2].textContent=x.confidence;const kind=document.createElement('select');
state.catalog.input_kinds.forEach(value=>{const option=document.createElement('option');option.value=value;
option.textContent=value.replaceAll('_',' ');kind.append(option)});kind.value='TRACK';
let form=null;kind.onchange=()=>{state.inputKinds[data.token]=kind.value;const positional=
['TRACK','OFFICIAL_OBSERVATION'].includes(kind.value);if(form)form.style.display=positional?'':'none';
const qc=d.querySelector('.qc');if(qc)qc.style.display=positional?'':'none';strong[2].textContent=
positional?x.confidence:'SEMANTIC TYPE'};
state.inputKinds[data.token]='TRACK';d.append(kind);
if(x.requires_confirmation){form=document.createElement('div');
form.className='warning';const why=document.createElement('div');why.textContent='Confirm schema: '+
x.reasons.join('; ');form.append(why);const fields=['latitude','longitude','timestamp_start','entity_id'];
const selects={};fields.forEach(field=>{const label=document.createElement('label');label.textContent=field+' ';
const select=document.createElement('select');select.style.margin='4px 0';const blank=document.createElement('option');
blank.value='';blank.textContent='— choose column —';select.append(blank);x.columns.forEach(column=>{const option=
document.createElement('option');option.value=column;option.textContent=column;option.selected=
x.detected_fields[field]===column;select.append(option)});selects[field]=select;label.append(select);form.append(label)});
const confirm=document.createElement('button');confirm.className='secondary';confirm.textContent='Confirm schema';
confirm.onclick=e=>{e.preventDefault();const map={};Object.entries(selects).forEach(([k,v])=>{
if(v.value)map[k]=v.value});if(!map.latitude||!map.longitude||!map.timestamp_start||!map.entity_id){
why.textContent='Latitude, longitude, timestamp and entity ID are required.';return}state.fieldMaps[data.token]=map;
fetch('/api/qc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:data.token,
field_map:map})}).then(r=>r.json()).then(result=>{if(!result.ok){showError(result);return}form.remove();
strong[2].textContent='CONFIRMED';renderQC(d,result.qc_summary)})};form.append(confirm);d.append(form)}
$('files').append(d);if(data.qc_summary)renderQC(d,data.qc_summary)}
function renderQC(card,q){const old=card.querySelector('.qc');if(old)old.remove();const box=document.createElement('div');
box.className='qc metrics';[['cleaned_positions','valid positions'],['large_gaps','gaps > 6h'],
['track_segments','segments']].forEach(([key,label])=>{const m=document.createElement('div');m.className='metric';
const strong=document.createElement('strong');strong.textContent=q[key];const small=document.createElement('small');
small.textContent=label;m.append(strong,small);box.append(m)});card.append(box)}
function selected(kind){return [...document.querySelectorAll('input[data-kind="'+kind+'"]:checked')]
.map(x=>x.value)}
function payload(){let custom=null;if($('area').value==='custom'){custom=$('customExtent').value.split(',')
.map(Number)}return{area:$('area').value,background:$('background').value,
maritime_layers:selected('layer'),outputs:selected('output'),custom_extent:custom,
context_layers:selected('context'),start_date:$('startDate').value||null,end_date:$('endDate').value||null,
upload_tokens:state.uploads.map(x=>x.token),field_maps:state.fieldMaps,input_kinds:state.inputKinds,
input_metadata:state.inputMetadata}}
function updatePreview(){if(!state.catalog)return;const area=state.catalog.areas.find(x=>x.id===$('area').value);
$('areaLabel').textContent=area.label;$('areaPurpose').textContent=area.purpose||'Define coordinates below';
$('profile').textContent=(area.profile||'adaptive').toUpperCase()+' · CANONICAL QGIS OUTPUT';
const chips=$('chips');chips.innerHTML='';selected('layer').forEach(id=>{const c=document.createElement('span');
c.className='chip';c.textContent=state.catalog.maritime_layers.find(x=>x.id===id).label;chips.append(c)});
selected('context').forEach(id=>{const all=Object.values(state.catalog.context_layer_groups).flat();
const c=document.createElement('span');c.className='chip';c.textContent=all.find(x=>x.layer_id===id).dataset;
chips.append(c)});
drawTracks();const bg=$('background').value;$('preview').style.filter=bg==='minimal-grayscale'?'grayscale(1)':'none';
$('preview').style.background=bg==='none'?'#fffdf7':''}
function drawTracks(){const points=state.uploads.flatMap(x=>x.inspection.sample_positions||[]),svg=$('trackSvg');
svg.innerHTML='';if(points.length<1)return;const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
let minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
if(minx===maxx){minx-=1;maxx+=1}if(miny===maxy){miny-=1;maxy+=1}const coords=points.map(p=>
[(p[0]-minx)/(maxx-minx)*82+9,91-(p[1]-miny)/(maxy-miny)*82]);
const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',
coords.map(p=>p.join(',')).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#b84935');
line.setAttribute('stroke-width','1.7');line.setAttribute('vector-effect','non-scaling-stroke');
svg.setAttribute('viewBox','0 0 100 100');svg.append(line)}
async function build(){$('build').disabled=true;$('message').textContent='Building with headless QGIS…';
$('details').classList.add('hidden');try{const r=await fetch('/api/build',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});const data=await r.json();
if(!data.ok){showError(data);return}$('message').textContent='Build complete and verified.';
$('details').textContent=JSON.stringify(data,null,2);$('details').classList.remove('hidden')}
catch(e){showError({error:e.name,message:e.message})}finally{$('build').disabled=false}}
function showError(x){$('message').textContent='Stopped safely: '+x.message;$('details').textContent=
JSON.stringify(x,null,2);$('details').classList.remove('hidden');$('build').disabled=false}
init().catch(showError);
</script>
</body></html>"""


if __name__ == "__main__":
    main()
