import html
import re
from pathlib import Path
from xml.sax.saxutils import escape

from . import geo


def gpx(plan):
    pts = plan["route"]["coords"]
    wpts = []
    for s in plan["ride"]["stops"]:
        p = geo.place(s["place"])[1]
        wpts.append(f'  <wpt lat="{p["lat"]}" lon="{p["lon"]}"><name>{escape(s["place"])}</name>'
                    f'<desc>{escape(s["do"])}</desc></wpt>')
    trk = "\n".join(f'      <trkpt lat="{a}" lon="{b}"/>' for a, b in pts)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="ridecard" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>{escape(plan['ride']['name'])}</name></metadata>
{chr(10).join(wpts)}
  <trk><name>{escape(plan['ride']['name'])}</name>
    <trkseg>
{trk}
    </trkseg>
  </trk>
</gpx>
"""


def _md_to_html(md):
    out, in_list = [], False
    for line in md.splitlines():
        line = html.escape(line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        if line.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{line[2:]}</li>")
        elif line.strip():
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def sketch_svg(plan, w=320, h=220, pad=60):
    """Route outline drawn from the GPX points. No map tiles, prints fine in black and white."""
    pts = plan["route"]["coords"]
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    lat0, lat1, lon0, lon1 = min(lats), max(lats), min(lons), max(lons)
    sx = (w - 2 * pad) / max(lon1 - lon0, 1e-6); sy = (h - 2 * pad) / max(lat1 - lat0, 1e-6)
    s = min(sx, sy)
    ox = (w - (lon1 - lon0) * s) / 2  # center the outline in the box
    oy = (h - (lat1 - lat0) * s) / 2
    def xy(lat, lon):
        return ox + (lon - lon0) * s, h - oy - (lat - lat0) * s
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(a, b) for a, b in pts[::3]))
    dots = []
    for st in plan["ride"]["stops"]:
        p = geo.place(st["place"])[1]; x, y = xy(p["lat"], p["lon"])
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#2f6b3a"/><text x="{x+8:.1f}" y="{y+4:.1f}" font-size="10">{html.escape(st["place"])}</text>')
    sp = geo.place(plan["req"]["start"])[1]; x, y = xy(sp["lat"], sp["lon"])
    dots.append(f'<rect x="{x-5:.1f}" y="{y-5:.1f}" width="10" height="10" fill="#b5532b"/><text x="{x+8:.1f}" y="{y+4:.1f}" font-size="10">{html.escape(plan["req"]["start"])}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Route outline">'
            f'<polyline points="{path}" fill="none" stroke="#222" stroke-width="2" stroke-linejoin="round"/>{"".join(dots)}</svg>')


def start_by(plan):
    """Latest start time that gets you home 30 minutes before sunset."""
    wx = plan["weather"]
    if not wx:
        return "early"
    h, m = map(int, wx["sunset"].split(":"))
    t = h * 60 + m - 30 - plan["ride_min"] - plan["stop_min"]
    return f"{t // 60}:{t % 60:02d}" if t > 0 else "sunrise"


def card_html(plan):
    r, wx = plan["route"], plan["weather"]
    miles = round(r["km"] * 0.621)
    wx_line = (f"{wx['low_f']:.0f}F to {wx['high_f']:.0f}F, {wx['rain_pct']}% rain, gusts {wx['gust_mph']:.0f} mph, sunset {wx['sunset']}"
               if wx else "No forecast pulled")
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(plan['ride']['name'])} ride card</title>
<style>
body{{font:15px/1.45 Georgia,serif;max-width:720px;margin:24px auto;padding:0 16px;color:#1d1d1b;background:#fbf8f1}}
h1{{font-size:26px;margin:0}} .meta{{color:#555;margin:4px 0 14px}} h2{{font-size:16px;text-transform:uppercase;letter-spacing:.06em;border-top:2px solid #1d1d1b;padding-top:6px;margin-top:18px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .box{{border:1px solid #1d1d1b;padding:8px}} small{{color:#666}}
@media (max-width:560px){{.grid{{grid-template-columns:1fr}}}} @media print{{body{{background:#fff}}}}
</style></head><body>
<h1>{html.escape(plan['ride']['name'])}</h1>
<div class="meta">{html.escape(plan['req']['date'])} · from {html.escape(plan['req']['start'])} · {miles} mi · {plan['ride_min']/60:.1f} h riding + {plan['stop_min']/60:.1f} h on foot</div>
<div class="grid"><div class="box">{sketch_svg(plan)}</div><div class="box"><b>Weather</b><br>{html.escape(wx_line)}<br><br><b>Total day</b><br>{(plan['ride_min']+plan['stop_min'])/60:.1f} hours. Leave by {html.escape(start_by(plan))} to be home before dark</div></div>
{_md_to_html(plan['card'])}
<p><small>Planned locally with {html.escape(plan['model'])}. Routes from OpenStreetMap via OSRM, weather from Open-Meteo. Load the GPX on your nav, put the phone away.</small></p>
</body></html>"""


def write_all(plan, outdir="out"):
    out = Path(outdir); out.mkdir(exist_ok=True)
    stem = f"{plan['req']['date']}-{plan['ride']['id']}"
    (out / f"{stem}.gpx").write_text(gpx(plan))
    (out / f"{stem}.md").write_text(f"# {plan['ride']['name']}\n\n" + plan["card"] + "\n")
    (out / f"{stem}.html").write_text(card_html(plan))
    return [out / f"{stem}.{x}" for x in ("html", "gpx", "md")]
