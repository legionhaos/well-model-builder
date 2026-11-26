#!/usr/bin/env python3
"""Live TZ benchmark & adversarial checker for Well Model Builder services."""

from __future__ import annotations

import copy
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
IPR_URL = os.getenv("IPR_URL", "http://localhost:8003").rstrip("/")
VLP_URL = os.getenv("VLP_URL", "http://localhost:8002").rstrip("/")
NODAL_URL = os.getenv("NODAL_URL", "http://localhost:8004").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:18080").rstrip("/")


def load_well_01() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    req = REPO_ROOT / "test_data" / "well_01" / "requests"
    exp = REPO_ROOT / "test_data" / "well_01" / "expected"
    return (
        json.loads((req / "ipr.json").read_text(encoding="utf-8")),
        json.loads((req / "vlp.json").read_text(encoding="utf-8")),
        json.loads((req / "nodal.json").read_text(encoding="utf-8")),
        json.loads((exp / "nodal.json").read_text(encoding="utf-8"))[0],
    )


def assert_4xx_json(resp: httpx.Response, label: str) -> None:
    if not (400 <= resp.status_code < 500):
        raise AssertionError(f"[{label}] expected 4xx, got {resp.status_code}: {resp.text[:200]}")
    ct = resp.headers.get("content-type", "")
    if "application/json" not in ct:
        raise AssertionError(f"[{label}] expected application/json, got {ct}")
    if "<html" in resp.text.lower() or not resp.text.strip():
        raise AssertionError(f"[{label}] invalid error body: {resp.text[:200]}")
    body = resp.json()
    if not any(k in body for k in ("message", "description", "detail")):
        raise AssertionError(f"[{label}] missing message/description/detail in {body}")


def measure_latency(client: httpx.Client, method: str, url: str, payload: dict[str, Any], runs: int = 10) -> dict[str, float]:
    times: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        r = client.request(method, url, json=payload)
        r.raise_for_status()
        times.append((time.perf_counter() - t0) * 1000.0)
    times_sorted = sorted(times)
    p95_idx = min(len(times_sorted) - 1, max(0, int(0.95 * len(times_sorted)) - 1))
    return {
        "min_ms": round(min(times), 2),
        "p50_ms": round(statistics.median(times), 2),
        "p95_ms": round(times_sorted[p95_idx], 2),
        "max_ms": round(max(times), 2),
    }


def main() -> int:
    ipr_req, vlp_req, nodal_req, nodal_exp = load_well_01()
    full_req = {"ipr": ipr_req, "vlp": vlp_req}
    passed: list[str] = []
    failed: list[str] = []

    with httpx.Client(timeout=30.0) as client:
        # 1. Accuracy & Latency Benchmark
        try:
            r_calc = client.post(f"{BACKEND_URL}/api/calculate", json=full_req)
            r_calc.raise_for_status()
            calc = r_calc.json()
            op = calc["operating_point"]
            err_q = abs(op["q_liq"] - nodal_exp["q_liq"]) / nodal_exp["q_liq"] * 100.0
            err_p = abs(op["p_wf"] - nodal_exp["p_wf"]) / nodal_exp["p_wf"] * 100.0
            assert err_q <= 1.0 and err_p <= 2.0, f"Accuracy out of range: q={err_q:.2f}%, p={err_p:.2f}%"

            lat_ipr = measure_latency(client, "POST", f"{IPR_URL}/ipr/calc", ipr_req)
            lat_vlp = measure_latency(client, "POST", f"{VLP_URL}/vlp/calc", vlp_req)
            lat_nodal = measure_latency(client, "POST", f"{NODAL_URL}/nodal/calc", nodal_req)
            lat_e2e = measure_latency(client, "POST", f"{BACKEND_URL}/api/calculate", full_req)
            print("=== 1. ACCURACY & LATENCY BENCHMARK (10 runs each) ===")
            print(f"well_01 Operating Point : q_liq = {op['q_liq']} m3/d (err {err_q:.2f}%), p_wf = {op['p_wf']} atm (err {err_p:.2f}%)")
            print(f"IPR   /ipr/calc         : {lat_ipr}")
            print(f"VLP   /vlp/calc         : {lat_vlp}")
            print(f"Nodal /nodal/calc       : {lat_nodal}")
            print(f"E2E   /api/calculate    : {lat_e2e}")
            passed.append("Accuracy & Latency (IPR/VLP/Nodal/E2E)")
        except Exception as exc:
            failed.append(f"Accuracy & Latency: {exc}")

        # 2. Boundary points [2..201] & malformed 4xx JSON contract
        try:
            for pts in (2, 21, 201):
                ri = client.post(f"{IPR_URL}/ipr/calc", json={**ipr_req, "points": pts})
                assert ri.status_code == 200 and len(ri.json()["q_liq"]) == pts
                rv = client.post(f"{VLP_URL}/vlp/calc", json={**vlp_req, "points": pts})
                assert rv.status_code == 200 and len(rv.json()["q_liq"]) == pts

            for bad_pts in (0, 1, 202):
                assert_4xx_json(client.post(f"{IPR_URL}/ipr/calc", json={**ipr_req, "points": bad_pts}), f"IPR points={bad_pts}")
                assert_4xx_json(client.post(f"{VLP_URL}/vlp/calc", json={**vlp_req, "points": bad_pts}), f"VLP points={bad_pts}")

            for url, lbl in [
                (f"{IPR_URL}/ipr/calc", "IPR"),
                (f"{VLP_URL}/vlp/calc", "VLP"),
                (f"{NODAL_URL}/nodal/calc", "Nodal"),
                (f"{BACKEND_URL}/api/calculate", "Backend"),
            ]:
                for raw, ctype, tag in [
                    (b"{broken", "application/json", "broken-json"),
                    (b"", "application/json", "empty-body"),
                    (b"{}", "application/json", "empty-dict"),
                    (b"garbage text", "text/plain", "text-plain"),
                ]:
                    r_bad = client.post(url, content=raw, headers={"Content-Type": ctype})
                    assert_4xx_json(r_bad, f"{lbl}:{tag}")
            passed.append("TZ Section 5 points [2..201] & 4xx JSON error contract (IPR/VLP/Nodal/Backend)")
        except Exception as exc:
            failed.append(f"Boundaries & 4xx JSON: {exc}")

        # 3. Incomplete JSON / text / nonsense / non-physical handling
        try:
            # 3a. Incomplete payload on /api/calculate
            assert_4xx_json(client.post(f"{BACKEND_URL}/api/calculate", json={"ipr": {"p_res": 200, "wct": 50}}), "Incomplete /api/calculate")

            # 3b. Incomplete JSON & incomplete inline text sent to /api/chat WITH well_01 form params loaded
            for msg in [
                '{"ipr": {"p_res": 220, "wct": 40}}',
                "Рассчитай модель: p_res=235 атм, wct=35%, pi=1.6",
            ]:
                rc = client.post(f"{BACKEND_URL}/api/chat", json={"message": msg, "params": full_req})
                assert rc.status_code == 200
                body = rc.json()
                assert "Уточните параметры" in body["text"] and "Без вашего согласия" in body["text"], f"Unexpected chat response: {body}"
                assert body["calculation_result"]["operating_point"] is None

                rcs = client.post(f"{BACKEND_URL}/api/chat/stream", json={"message": msg, "params": full_req})
                assert rcs.status_code == 200 and "Уточните параметры" in rcs.text

            # 3c. Nonsense / greeting never triggers fake calculations
            rn = client.post(f"{BACKEND_URL}/api/chat", json={"message": "прпрп", "params": full_req})
            assert rn.status_code == 200 and rn.json()["calculation_result"] is None

            # 3d. Non-intersecting well & non-physical WCT flagging
            presets = client.get(f"{BACKEND_URL}/api/presets").json()
            no_int = next(p["data"] for p in presets if p["id"] == "well_no_intersection")
            r_no = client.post(f"{BACKEND_URL}/api/calculate", json=no_int)
            assert r_no.status_code == 200 and r_no.json()["status"] == "no_intersection" and r_no.json()["operating_point"] is None

            wct_bad = copy.deepcopy(full_req)
            wct_bad["vlp"]["pvt"]["wct"] = 85.0
            r_mis = client.post(f"{BACKEND_URL}/api/calculate", json=wct_bad)
            assert r_mis.status_code == 200 and r_mis.json()["meta"]["is_physical"] is False
            passed.append("Incomplete JSON/text, nonsense chat, no-intersection & non-physical diagnostics")
        except Exception as exc:
            failed.append(f"Incomplete / Edge cases: {exc}")

        # 4. Offline multi-format import check (all files in test_import_files/)
        try:
            imp_dir = REPO_ROOT / "test_import_files"
            imported = 0
            for path in sorted(imp_dir.iterdir()):
                if path.suffix.lower() in {".wav", ".ogg"}:
                    r = client.post(f"{BACKEND_URL}/api/enhancements/audio", files={"file": (path.name, path.read_bytes())})
                    assert r.status_code == 200, f"{path.name}: {r.text}"
                elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    r = client.post(f"{BACKEND_URL}/api/enhancements/vision", files={"file": (path.name, path.read_bytes())})
                    assert r.status_code == 200, f"{path.name}: {r.text}"
                else:
                    r = client.post(f"{BACKEND_URL}/api/chat/upload", files={"file": (path.name, path.read_bytes())})
                    assert r.status_code == 200 and r.json()["parsed_params"] is not None, f"{path.name}: {r.text}"
                imported += 1
            passed.append(f"Offline multi-format import pack ({imported} files incl. PDF OCR & Whisper Tiny)")
        except Exception as exc:
            failed.append(f"Multi-format import: {exc}")

    print("\n=== BENCHMARK SUMMARY ===")
    for item in passed:
        print(f"  [PASS] {item}")
    for item in failed:
        print(f"  [FAIL] {item}")

    if failed:
        return 1
    print("\nALL LIVE BENCHMARKS PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
