#!/usr/bin/env python3
"""Phase 13 gate: many field users syncing at once.

Simulates DEVICES phones, each pushing its captures in batches and pulling,
all at the same time, against a running stack. Some batches are sent twice,
as a phone does after a lost reply. Checks that every capture arrives exactly
once, nothing fails, and responses stay within the target.

    scripts/load-sync.py [--api http://localhost:8000/api] [--devices 20] [--captures 25]

Needs the demo accounts (`make seed`). Uses only the standard library.
"""

import argparse
import json
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

P95_TARGET_S = 3.0


def call(api, method, path, token=None, district=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if district:
        headers["X-District-ID"] = str(district)
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{api}{path}", data=data, headers=headers, method=method)  # noqa: S310
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            return response.status, json.load(response), time.perf_counter() - start
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode(errors="replace")[:300]}, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000/api")
    parser.add_argument("--devices", type=int, default=20)
    parser.add_argument("--captures", type=int, default=25)
    parser.add_argument("--password", default="Demo-Pass-2026!")
    args = parser.parse_args()

    status, tokens, _ = call(args.api, "POST", "/auth/login/", body={"email": "sma.planner@example.test", "password": args.password})
    if status != 200:
        print("sign-in failed:", status, tokens)
        return 1
    token = tokens["access"]
    _, me, _ = call(args.api, "GET", "/auth/me/", token)
    district = me["memberships"][0]["district"]["id"]
    _, project, _ = call(args.api, "POST", "/projects/", token, district, {"name": f"Sync load {int(time.time())}"})
    _, layer, _ = call(args.api, "POST", "/layers/", token, district, {"project": project["id"], "name": "Pegs", "geometry_type": "point", "schema": [{"name": "pid", "type": "text"}]})

    latencies: list[float] = []
    problems: list[str] = []
    applied: set[str] = set()
    lock = threading.Lock()
    start_together = threading.Barrier(args.devices)

    def device(number: int) -> None:
        rng = random.Random(number)
        changes = [
            {
                "change_id": str(uuid.uuid4()),
                "op": "create",
                "layer": layer["id"],
                "feature_uuid": str(uuid.uuid4()),
                "geometry": {"type": "Point", "coordinates": [-0.2 + rng.random() / 100, 5.6 + rng.random() / 100]},
                "properties": {"pid": f"D{number}-{i}"},
                "capture": {"method": "gps", "accuracy_m": 3.5, "readings": 5},
            }
            for i in range(args.captures)
        ]
        start_together.wait()
        for at in range(0, len(changes), 5):
            batch = changes[at : at + 5]
            # One batch in five is sent twice (the reply to the first was "lost").
            for _attempt in range(2 if rng.random() < 0.2 else 1):
                code, body, seconds = call(args.api, "POST", "/sync/push/", token, district, {"device_id": f"load-{number}", "changes": batch})
                with lock:
                    latencies.append(seconds)
                    if code != 200:
                        problems.append(f"push HTTP {code}: {body}")
                        continue
                    for result in body["results"]:
                        if result["status"] != "applied":
                            problems.append(f"not applied: {result}")
                        else:
                            applied.add(result["feature"]["uuid"])
        code, body, seconds = call(args.api, "GET", f"/sync/pull/?project={project['id']}", token, district)
        with lock:
            latencies.append(seconds)
            if code != 200:
                problems.append(f"pull HTTP {code}: {body}")

    threads = [threading.Thread(target=device, args=(n,)) for n in range(args.devices)]
    began = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - began

    expected = args.devices * args.captures
    _, listing, _ = call(args.api, "GET", f"/layers/{layer['id']}/features/?limit=1", token, district)
    on_server = listing.get("numberMatched")
    p95 = statistics.quantiles(latencies, n=20)[18]
    print(f"{args.devices} devices, {expected} captures, {len(latencies)} requests in {elapsed:.1f} s")
    print(f"response time: median {statistics.median(latencies):.2f} s, 95th percentile {p95:.2f} s (target {P95_TARGET_S} s), slowest {max(latencies):.2f} s")
    print(f"on the server: {on_server} features (expected {expected}); applied results: {len(applied)}")
    if on_server != expected or len(applied) != expected:
        problems.append(f"expected {expected} features, the server has {on_server}")
    if p95 > P95_TARGET_S:
        problems.append(f"95th percentile {p95:.2f} s is over the {P95_TARGET_S} s target")
    for problem in problems[:10]:
        print("PROBLEM:", problem)
    print("PASSED" if not problems else f"FAILED ({len(problems)} problems)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
