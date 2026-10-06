"""Pre-fetch road geometry for every ride from common starts so ridecard works with no signal."""
import sys, time
sys.path.insert(0, ".")
from ridecard import geo, planner
starts = sys.argv[1:] or ["Boerne", "San Antonio"]
for s in starts:
    for ride in planner.RIDES:
        r = geo.route(planner.waypoints(ride, s))
        print(f"{s:12s} {ride['id']:24s} {r['km']*0.621:6.0f} mi {r['minutes']/60:5.1f} h  {len(r['coords'])} pts")
        time.sleep(1)
