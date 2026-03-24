"""
generate_html.py
Creates self-contained interactive Leaflet.js HTML maps for each day's outlook.
Each file is fully embeddable via <iframe> with no external file dependencies
beyond the Leaflet CDN.
"""

import json
import os
import sys
from datetime import datetime, timezone

# ── Color / label config (mirrors generate_png.py) ────────────────────────────

CATEGORICAL_COLORS = {
    "TSTM": {"fill": "#C1E9C1", "stroke": "#4A8F4A", "label": "Thunderstorm"},
    "MRGL": {"fill": "#66A366", "stroke": "#2E6B2E", "label": "Marginal"},
    "SLGT": {"fill": "#FFE066", "stroke": "#C8A800", "label": "Slight"},
    "ENH":  {"fill": "#FFA500", "stroke": "#C06000", "label": "Enhanced"},
    "MDT":  {"fill": "#E8000D", "stroke": "#8B0000", "label": "Moderate"},
    "HIGH": {"fill": "#FF00FF", "stroke": "#9900CC", "label": "High"},
}

PROB_COLORS = {
    "0.02": {"fill": "#008B00", "stroke": "#005500", "label": "2%"},
    "0.05": {"fill": "#8B4513", "stroke": "#5C2C0A", "label": "5%"},
    "0.10": {"fill": "#FFD700", "stroke": "#B89B00", "label": "10%"},
    "0.15": {"fill": "#FF4500", "stroke": "#C02000", "label": "15%"},
    "0.30": {"fill": "#FF0000", "stroke": "#8B0000", "label": "30%"},
    "0.45": {"fill": "#FF00FF", "stroke": "#9900CC", "label": "45%"},
    "0.60": {"fill": "#800080", "stroke": "#4B004B", "label": "60%"},
}

TYPE_META = {
    "categorical":   {"title": "Categorical",   "colors": CATEGORICAL_COLORS},
    "tornado":       {"title": "Tornado Prob.",  "colors": PROB_COLORS},
    "wind":          {"title": "Wind Prob.",     "colors": PROB_COLORS},
    "hail":          {"title": "Hail Prob.",     "colors": PROB_COLORS},
    "probabilistic": {"title": "Probabilistic", "colors": PROB_COLORS},
}

LAYER_PRIORITY = ["categorical", "tornado", "wind", "hail", "probabilistic"]


def _normalise_label(label):
    """Convert numeric labels like '10.00' to canonical '0.10' form."""
    try:
        val = float(label)
        if val > 1:
            val /= 100
        return f"{val:.2f}"
    except (ValueError, TypeError):
        return label


def _geojson_style_js(geojson, colors):
    """Inject fill/stroke into each feature's properties for Leaflet styling."""
    features = (geojson or {}).get("features", [])
    patched = []
    for feat in features:
        props = dict(feat.get("properties") or {})
        raw_label = props.get("LABEL", "")
        label = _normalise_label(raw_label)
        entry = colors.get(raw_label) or colors.get(label) or {}
        props["_fill"]   = props.get("fill")   or entry.get("fill",   "#CCCCCC")
        props["_stroke"] = props.get("stroke") or entry.get("stroke", "#888888")
        props["_label"]  = entry.get("label") or props.get("LABEL2") or raw_label
        props["_is_sig"] = "SIG" in raw_label.upper() or props.get("LABEL2", "").upper().startswith("SIG")
        patched.append({**feat, "properties": props})
    return {**geojson, "features": patched}


def _legend_items_js(colors):
    items = []
    for key, meta in colors.items():
        items.append({"key": key, "fill": meta["fill"], "label": meta["label"]})
    # Deduplicate by label
    seen = set()
    unique = []
    for item in items:
        if item["label"] not in seen:
            unique.append(item)
            seen.add(item["label"])
    return unique


def build_html(day, layers_data, fetched_utc=""):
    """
    layers_data: dict of {outlook_type: geojson_dict | None}
    Returns a complete HTML string.
    """
    # Prepare JS data blobs
    js_layers = {}
    for otype, geojson in layers_data.items():
        if geojson is None:
            js_layers[otype] = None
            continue
        meta = TYPE_META.get(otype, {"colors": PROB_COLORS})
        js_layers[otype] = _geojson_style_js(geojson, meta["colors"])

    day_label = f"Day {day}"
    fetch_note = f"Data fetched: {fetched_utc[:16].replace('T', ' ')} UTC" if fetched_utc else ""

    # Build tab list
    available_types = [t for t in LAYER_PRIORITY if t in layers_data and layers_data[t]]
    if not available_types:
        available_types = list(layers_data.keys())

    tab_buttons = ""
    for otype in available_types:
        label = TYPE_META.get(otype, {}).get("title", otype.title())
        active = "active" if otype == available_types[0] else ""
        tab_buttons += f'<button class="tab-btn {active}" data-type="{otype}">{label}</button>\n'

    # Legend configs per type
    legend_configs = {}
    for otype in available_types:
        meta = TYPE_META.get(otype, {"colors": PROB_COLORS})
        legend_configs[otype] = _legend_items_js(meta["colors"])

    data_json  = json.dumps(js_layers, separators=(",", ":"))
    legend_json = json.dumps(legend_configs, separators=(",", ":"))
    avail_json = json.dumps(available_types)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>SPC {day_label} Outlook</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;flex-direction:column;height:100vh}}
#header{{background:linear-gradient(135deg,#16213e,#0f3460);padding:10px 16px;border-bottom:2px solid #e94560;flex-shrink:0}}
#header h1{{font-size:1.1rem;font-weight:700;color:#fff;letter-spacing:0.5px}}
#header p{{font-size:0.72rem;color:#aaa;margin-top:2px}}
#tabs{{display:flex;gap:4px;padding:8px 12px;background:#16213e;flex-shrink:0;flex-wrap:wrap}}
.tab-btn{{padding:5px 14px;border:1px solid #0f3460;border-radius:20px;background:#0f3460;color:#bbb;
          cursor:pointer;font-size:0.78rem;transition:all .2s;white-space:nowrap}}
.tab-btn:hover{{background:#e94560;color:#fff;border-color:#e94560}}
.tab-btn.active{{background:#e94560;color:#fff;border-color:#e94560;font-weight:600}}
#map{{flex:1;min-height:0}}
#legend{{position:absolute;bottom:24px;right:10px;z-index:1000;background:rgba(22,33,62,0.92);
         border:1px solid #0f3460;border-radius:8px;padding:10px 14px;min-width:130px;
         box-shadow:0 2px 12px rgba(0,0,0,0.5)}}
#legend h4{{font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;color:#aaa;
            margin-bottom:8px;border-bottom:1px solid #333;padding-bottom:4px}}
.legend-row{{display:flex;align-items:center;gap:8px;margin-bottom:5px}}
.legend-swatch{{width:18px;height:14px;border-radius:3px;flex-shrink:0;border:1px solid rgba(255,255,255,0.15)}}
.legend-label{{font-size:0.75rem;color:#ddd}}
.sig-swatch{{background:repeating-linear-gradient(45deg,transparent,transparent 3px,rgba(0,0,0,0.4) 3px,rgba(0,0,0,0.4) 4px);
             border:1px solid #888}}
#no-data{{display:none;position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
          z-index:999;text-align:center;color:#888;font-size:1rem}}
#info-bar{{position:absolute;bottom:24px;left:10px;z-index:1000;background:rgba(22,33,62,0.85);
           border:1px solid #0f3460;border-radius:6px;padding:6px 10px;
           font-size:0.72rem;color:#aaa;max-width:260px;display:none}}
</style>
</head>
<body>
<div id="header">
  <h1>&#9928; SPC {day_label} Convective Outlook</h1>
  <p id="fetch-note">{fetch_note}</p>
</div>
<div id="tabs">{tab_buttons}</div>
<div style="position:relative;flex:1;min-height:0">
  <div id="map"></div>
  <div id="no-data">No outlook data available for this product.</div>
  <div id="legend"><h4>Legend</h4><div id="legend-items"></div></div>
  <div id="info-bar"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV/XN2GqnU=" crossorigin=""></script>
<script>
(function(){{
var LAYERS_DATA   = {data_json};
var LEGEND_CONFIG = {legend_json};
var AVAILABLE     = {avail_json};

var map = L.map('map',{{zoomControl:true,attributionControl:true}})
           .setView([37.5,-96],4);

// Basemap – CartoDB Positron (no labels, clean)
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_nolabels/{{z}}/{{x}}/{{y}}{{r}}.png',{{
  attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
  subdomains:'abcd', maxZoom:19
}}).addTo(map);

// Label overlay on top of outlook
var labelLayer = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_only_labels/{{z}}/{{x}}/{{y}}{{r}}.png',{{
  subdomains:'abcd', maxZoom:19, pane:'shadowPane'
}}).addTo(map);

var activeLayer = null;
var currentType = AVAILABLE[0] || null;

function normaliseLabel(lbl){{
  var n = parseFloat(lbl);
  if (!isNaN(n) && n > 1) n /= 100;
  if (!isNaN(n)) return n.toFixed(2);
  return lbl;
}}

function getStyle(feature){{
  var p = feature.properties || {{}};
  var fill   = p._fill   || '#CCCCCC';
  var stroke = p._stroke || '#888888';
  return {{
    fillColor:   fill,
    fillOpacity: 0.72,
    color:       stroke,
    weight:      0.8,
    opacity:     1
  }};
}}

function onEachFeature(feature,layer){{
  var p = feature.properties || {{}};
  var name = p._label || p.LABEL2 || p.LABEL || '';
  var isSig = p._is_sig;
  var tooltip = '<strong>' + (isSig ? 'Significant ' : '') + name + '</strong>';
  layer.bindTooltip(tooltip,{{sticky:true,opacity:0.92}});
  layer.on('mouseover',function(e){{
    var bar = document.getElementById('info-bar');
    bar.textContent = (isSig ? 'Significant ' : '') + name + ' Risk Area';
    bar.style.display = 'block';
  }});
  layer.on('mouseout',function(){{
    document.getElementById('info-bar').style.display='none';
  }});
}}

function buildSigHatch(geojson){{
  // overlay for significant areas
  var sigFeatures = (geojson.features||[]).filter(function(f){{
    return f.properties && f.properties._is_sig;
  }});
  if(!sigFeatures.length) return null;
  return L.geoJSON({{type:'FeatureCollection',features:sigFeatures}},{{
    style:function(){{return{{fillColor:'#000000',fillOpacity:0.15,color:'#000',weight:0.5,
                              dashArray:'3,3'}}}},
    pane:'overlayPane'
  }});
}}

function showLayer(type){{
  if(activeLayer){{ map.removeLayer(activeLayer); activeLayer=null; }}

  var data = LAYERS_DATA[type];
  var noDataEl = document.getElementById('no-data');

  if(!data || !data.features || !data.features.length){{
    noDataEl.style.display='block';
    updateLegend(type);
    return;
  }}
  noDataEl.style.display='none';

  var layer = L.geoJSON(data,{{
    style: getStyle,
    onEachFeature: onEachFeature
  }}).addTo(map);

  var sigLayer = buildSigHatch(data);
  if(sigLayer) sigLayer.addTo(map);

  activeLayer = type==='categorical'
    ? L.layerGroup([layer, sigLayer].filter(Boolean))
    : L.layerGroup([layer, sigLayer].filter(Boolean));

  updateLegend(type);
}}

function updateLegend(type){{
  var items = LEGEND_CONFIG[type] || [];
  var data  = LAYERS_DATA[type];
  var usedLabels = new Set();
  if(data && data.features){{
    data.features.forEach(function(f){{
      var lbl = (f.properties||{{}})._label;
      if(lbl) usedLabels.add(lbl);
    }});
  }}
  var container = document.getElementById('legend-items');
  container.innerHTML='';
  items.forEach(function(item){{
    if(usedLabels.size && !usedLabels.has(item.label)) return;
    var row=document.createElement('div'); row.className='legend-row';
    var sw=document.createElement('div');  sw.className='legend-swatch';
    sw.style.background=item.fill;
    var lb=document.createElement('span'); lb.className='legend-label';
    lb.textContent=item.label;
    row.appendChild(sw); row.appendChild(lb);
    container.appendChild(row);
  }});
  // Significant row
  var sigRow=document.createElement('div'); sigRow.className='legend-row';
  var sigSw=document.createElement('div');  sigSw.className='legend-swatch sig-swatch';
  var sigLb=document.createElement('span'); sigLb.className='legend-label';
  sigLb.textContent='Significant';
  sigRow.appendChild(sigSw); sigRow.appendChild(sigLb);
  container.appendChild(sigRow);
}}

// Tab switching
document.querySelectorAll('.tab-btn').forEach(function(btn){{
  btn.addEventListener('click',function(){{
    document.querySelectorAll('.tab-btn').forEach(function(b){{b.classList.remove('active')}});
    btn.classList.add('active');
    currentType = btn.dataset.type;
    showLayer(currentType);
  }});
}});

if(currentType) showLayer(currentType);

}})();
</script>
</body>
</html>"""

    return html


def generate_all(output_root="output"):
    """Generate interactive.html for every day that has at least one GeoJSON file."""
    for day in range(1, 9):
        day_dir = os.path.join(output_root, f"day{day}")
        if not os.path.isdir(day_dir):
            continue

        layers_data = {}
        fetched_utc = ""

        for otype in LAYER_PRIORITY:
            path = os.path.join(day_dir, f"{otype}.geojson")
            if os.path.exists(path):
                with open(path) as f:
                    data = json.load(f)
                layers_data[otype] = data
                if not fetched_utc:
                    fetched_utc = (data.get("_meta") or {}).get("fetched_utc", "")

        if not layers_data:
            continue

        print(f"Generating Day {day} interactive HTML …")
        html = build_html(day, layers_data, fetched_utc)
        dest = os.path.join(day_dir, "interactive.html")
        with open(dest, "w") as f:
            f.write(html)
        print(f"  Saved → {dest}")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "output"
    generate_all(root)
