import argparse
import sys

from . import llm, output, planner


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ridecard", description="Plan a Texas Hill Country motorcycle day ride with a local open-weight model, then put the phone away.")
    ap.add_argument("request", nargs="+", help='e.g. "5 hours from Boerne saturday, want fall color and a short hike"')
    ap.add_argument("--offline", action="store_true", help="use only cached routes, skip the forecast")
    ap.add_argument("--no-llm", action="store_true", help="skip the model, use keyword parsing and a template card")
    ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    text = " ".join(a.request)
    if not a.no_llm and not llm.available():
        print(f"[ridecard] no local model at {llm.BASE_URL}. Start Ollama (ollama run {llm.MODEL}) or pass --no-llm.", file=sys.stderr)
    p = planner.plan(text, offline=a.offline, use_llm=not a.no_llm)
    r = p["req"]
    print(f"[ridecard] understood: start={r['start']} hours={r['hours']} day={r.get('day')}->{r['date']} wants={r['wants']} avoid={r['avoid']}")
    files = output.write_all(p, a.out)
    print(f"\n{p['ride']['name']}  ({p['req']['start']}, {p['req']['date']})\n")
    print(p["card"])
    if p["alternates"]:
        print("\nAlso fits: " + "; ".join(f"{x['name']} ({x['total_hours']} h)" for x in p["alternates"]))
    print("\nWrote: " + ", ".join(str(f) for f in files))


if __name__ == "__main__":
    main()
