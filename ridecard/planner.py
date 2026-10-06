import datetime as dt
import json
import re
from pathlib import Path

from . import geo, llm

RIDES = json.loads((geo.DATA / "rides.json").read_text())
TAGS = ["foliage", "twisties", "sweepers", "water", "hike", "food", "history", "wildlife", "easy", "long"]
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

PARSE_PROMPT = """You turn a motorcycle rider's request into JSON. Reply with JSON only.
Keys:
  "start": one of {places}. Default "Boerne".
  "hours": total hours available for the day including stops, a number. Default 5.
  "day": "today", "tomorrow", a weekday name, or YYYY-MM-DD. Default "today".
  "wants": list from {tags}.
  "avoid": list from {tags}.
Map words to tags: leaves, color, maples, cypress -> foliage. curves, corners -> twisties. river, swim, lake -> water.
walk, hike, trail, view -> hike. lunch, bbq, eat -> food. bats, birds -> wildlife. chill, relaxed, short -> easy. all day -> long.
Request: {req}"""


def parse_request(text, use_llm=True):
    fallback = {"start": "Boerne", "hours": 5, "day": "today", "wants": [], "avoid": []}
    if use_llm:
        try:
            p = llm.chat_json([{"role": "user", "content": PARSE_PROMPT.format(
                places=", ".join(sorted(geo.PLACES)), tags=", ".join(TAGS), req=text)}])
            fallback.update({k: v for k, v in p.items() if v not in (None, "")})
        except Exception as e:  # small model hiccup: fall through to keyword parse
            print(f"[ridecard] model parse failed ({e}); using keyword parse")
            use_llm = False
    if not use_llm:
        low = text.lower()
        for name in geo.PLACES:
            if name.lower() in low:
                fallback["start"] = name
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hour)", low)
        if m:
            fallback["hours"] = float(m.group(1))
        for d in DAYS + ["tomorrow"]:
            if d in low:
                fallback["day"] = d
        kw = {"foliage": ["leaf", "leaves", "color", "maple", "cypress", "foliage"], "twisties": ["curv", "twist", "corner"],
              "water": ["river", "swim", "lake"], "hike": ["hike", "walk", "trail"], "food": ["lunch", "eat", "bbq", "food"],
              "wildlife": ["bat", "bird"], "easy": ["chill", "easy", "short"], "history": ["history", "old town"]}
        fallback["wants"] = [t for t, words in kw.items() if any(w in low for w in words)]
    # clean what the model gave back
    try:
        fallback["start"] = geo.place(str(fallback["start"]))[0]
    except KeyError:
        fallback["start"] = "Boerne"
    fallback["hours"] = float(fallback.get("hours") or 5)
    fallback["wants"] = [t for t in fallback.get("wants", []) if t in TAGS]
    fallback["avoid"] = [t for t in fallback.get("avoid", []) if t in TAGS]
    # Dates are arithmetic, not language. If the text names a day, trust code over the model.
    low = text.lower()
    named = [d for d in DAYS + ["tomorrow", "today"] if re.search(rf"\b{d}\b", low)]
    if named:
        fallback["day"] = named[0]
    fallback["date"] = resolve_day(str(fallback.get("day", "today")))
    return fallback


def resolve_day(day, today=None):
    today = today or dt.date.today()
    day = day.strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return day
    if day == "tomorrow":
        return (today + dt.timedelta(days=1)).isoformat()
    if day in DAYS:
        ahead = (DAYS.index(day) - today.weekday()) % 7
        return (today + dt.timedelta(days=ahead)).isoformat()
    return today.isoformat()


def waypoints(ride, start):
    via = [v for v in ride["via"]]
    return [start] + via + [start]


def ride_minutes(rt):
    # OSRM times are car times on open road. Add 15% for twisty roads and fuel.
    return round(rt["minutes"] * 1.15)


def rank(req, offline=False):
    month = int(req["date"][5:7])
    scored = []
    for ride in RIDES:
        rt = geo.route(waypoints(ride, req["start"]), offline=offline)
        if rt is None:
            continue
        stop_min = sum(s["minutes"] for s in ride["stops"])
        total = ride_minutes(rt) + stop_min
        score = 2 * len(set(req["wants"]) & set(ride["tags"])) - 3 * len(set(req["avoid"]) & set(ride["tags"]))
        score += 1 if month in ride["best_months"] else 0
        budget = req["hours"] * 60
        if total > budget:
            # trim stops before rejecting: you can always walk less
            score -= 1 + (total - budget) / 30
        scored.append({"ride": ride, "route": rt, "ride_min": ride_minutes(rt), "stop_min": stop_min,
                       "total_min": total, "score": round(score, 2)})
    scored.sort(key=lambda x: -x["score"])
    return scored


def go_call(wx):
    if not wx:
        return "No forecast (offline or more than two weeks out). Check the sky before you leave."
    notes = []
    if wx["rain_pct"] is not None and wx["rain_pct"] >= 50:
        notes.append(f"{wx['rain_pct']}% rain chance: low water crossings and caliche get slick, consider another day")
    if wx["gust_mph"] is not None and wx["gust_mph"] >= 35:
        notes.append(f"gusts to {wx['gust_mph']} mph: expect crosswinds on open ridges")
    if wx["low_f"] is not None and wx["low_f"] < 45:
        notes.append(f"low of {wx['low_f']}F: layers for the morning")
    if wx["high_f"] is not None and wx["high_f"] > 92:
        notes.append(f"high of {wx['high_f']}F: carry water, start early")
    verdict = "THINK TWICE" if any("consider another day" in n for n in notes) else "GO"
    return f"{verdict}. " + ("; ".join(notes) if notes else "Clean day for it.")


PLAN_PROMPT = """Write the opening of a motorcycle ride card. Exactly two sentences, second person, plain and direct, no em dashes.
Sentence 1: the ride, start town, miles and riding hours. Sentence 2: why this ride fits what the rider asked for and today's weather.
Use only these facts. Do not describe road surfaces, traffic, or businesses.
{facts}"""


def write_card(plan, use_llm=True):
    """The model writes the two sentences of prose. Facts (roads, stops, weather call) are filled by code so a small model cannot invent them."""
    miles = round(plan["route"]["km"] * 0.621)
    hrs = round(plan["ride_min"] / 60, 1)
    facts = {
        "rider_asked": plan["request_text"], "ride": plan["ride"]["name"], "start": plan["req"]["start"],
        "date": plan["req"]["date"], "miles": miles, "riding_hours": hrs,
        "matches": sorted(set(plan["req"]["wants"]) & set(plan["ride"]["tags"])),
        "weather": plan["weather"], "weather_call": plan["call"],
    }
    intro = f"{plan['ride']['name']} from {plan['req']['start']}: about {miles} miles and {hrs} hours of riding."
    if use_llm:
        try:
            intro = llm.chat([{"role": "user", "content": PLAN_PROMPT.format(facts=json.dumps(facts))}],
                             max_tokens=120, temperature=0.3).replace("\u2014", ",").strip()
        except Exception as e:
            print(f"[ridecard] model intro failed ({e}); using template")
    stops = "\n".join(f"- **{s['place']}** ({s['minutes']} min on foot): {s['do']}" for s in plan["ride"]["stops"])
    return (f"## The plan\n{intro}\n\n## Road notes\n- Route: {plan['ride']['roads']}.\n- {plan['ride']['season_note']}\n"
            f"- Load the GPX before you leave. The route is baked in, so it works with no signal.\n\n"
            f"## Get off the bike\n{stops}\n\n## Call\n{plan['call']}\n")


def plan(text, offline=False, use_llm=True):
    use_llm = use_llm and llm.available()
    req = parse_request(text, use_llm=use_llm)
    ranked = rank(req, offline=offline)
    if not ranked:
        raise SystemExit("No cached routes for that start. Plan once with signal, or start from Boerne or San Antonio.")
    best = ranked[0]
    s = geo.place(req["start"])[1]
    wx = None if offline else geo.forecast(s["lat"], s["lon"], req["date"])
    p = {"request_text": text, "req": req, **best, "weather": wx, "call": go_call(wx),
         "alternates": [{"name": r["ride"]["name"], "score": r["score"], "total_hours": round(r["total_min"] / 60, 1)} for r in ranked[1:3]],
         "model": llm.MODEL if use_llm else "none (template)"}
    p["card"] = write_card(p, use_llm=use_llm)
    return p
