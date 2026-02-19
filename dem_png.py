import math
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ===== 設定 =====
BBOX_W, BBOX_S, BBOX_E, BBOX_N = (
    144.124997317805,
    43.8750031560014,
    144.249993622593,
    43.9583319289041,
)

Z_MIN = 8
Z_MAX = 14

OUT_DIR = Path("raw_dem")   # raw_dem/{z}/{x}/{y}.png
BASE_URL = "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png"

MAX_WORKERS = 8            # 429が出るなら 4～6へ
TIMEOUT_SEC = 30
RETRIES = 5
BACKOFF_BASE = 1.6         # リトライ待ちの指数バックオフ
SLEEP_BETWEEN_REQ = 0.0    # サーバに優しくしたいなら 0.05 とか

# ===== タイル計算（XYZ）=====
def lon2tilex(lon: float, z: int) -> int:
    return int(math.floor((lon + 180.0) / 360.0 * (2 ** z)))

def lat2tiley(lat: float, z: int) -> int:
    lat_rad = math.radians(lat)
    n = math.tan(math.pi / 4 + lat_rad / 2)
    return int(math.floor((1 - math.log(n) / math.pi) / 2 * (2 ** z)))

def tile_range_for_bbox(w, s, e, n, z):
    x_min = lon2tilex(w, z)
    x_max = lon2tilex(e, z)
    # 注意: 北ほど y が小さい
    y_min = lat2tiley(n, z)
    y_max = lat2tiley(s, z)
    return x_min, x_max, y_min, y_max

def estimate_counts():
    total = 0
    per_z = {}
    for z in range(Z_MIN, Z_MAX + 1):
        x_min, x_max, y_min, y_max = tile_range_for_bbox(BBOX_W, BBOX_S, BBOX_E, BBOX_N, z)
        nx = x_max - x_min + 1
        ny = y_max - y_min + 1
        cnt = nx * ny
        per_z[z] = (nx, ny, cnt)
        total += cnt
    return per_z, total

# ===== ダウンロード =====
def download_one(session: requests.Session, z: int, x: int, y: int):
    url = BASE_URL.format(z=z, x=x, y=y)
    out_path = OUT_DIR / str(z) / str(x) / f"{y}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and out_path.stat().st_size > 0:
        return "skip", z, x, y

    for i in range(RETRIES):
        try:
            if SLEEP_BETWEEN_REQ > 0:
                time.sleep(SLEEP_BETWEEN_REQ)

            r = session.get(url, timeout=TIMEOUT_SEC)
            if r.status_code == 200:
                out_path.write_bytes(r.content)
                return "ok", z, x, y

            # 404は「そのタイルにデータが無い」可能性もあるので保存せずスキップ
            if r.status_code == 404:
                return "404", z, x, y

            # 429/5xx はリトライ
            if r.status_code in (429, 500, 502, 503, 504):
                wait = (BACKOFF_BASE ** i) + (0.05 * i)
                time.sleep(wait)
                continue

            return f"HTTP{r.status_code}", z, x, y

        except (requests.Timeout, requests.ConnectionError):
            wait = (BACKOFF_BASE ** i) + (0.05 * i)
            time.sleep(wait)
            continue

    return "fail", z, x, y

def run_download():
    tasks = []
    for z in range(Z_MIN, Z_MAX + 1):
        x_min, x_max, y_min, y_max = tile_range_for_bbox(BBOX_W, BBOX_S, BBOX_E, BBOX_N, z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tasks.append((z, x, y))

    print(f"Download tasks: {len(tasks):,} tiles")

    ok = skip = nf = fail = other = 0
    t0 = time.time()

    with requests.Session() as session:
        # 軽いUA（弾かれにくくする）
        session.headers.update({"User-Agent": "offline-dem-fetch/1.0"})
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(download_one, session, z, x, y) for (z, x, y) in tasks]
            for idx, f in enumerate(as_completed(futures), 1):
                status, z, x, y = f.result()
                if status == "ok":
                    ok += 1
                elif status == "skip":
                    skip += 1
                elif status == "404":
                    nf += 1
                elif status == "fail":
                    fail += 1
                else:
                    other += 1

                if idx % 500 == 0 or idx == len(tasks):
                    dt = time.time() - t0
                    print(
                        f"[{idx:,}/{len(tasks):,}] ok={ok:,} skip={skip:,} 404={nf:,} fail={fail:,} other={other:,}  ({dt:.1f}s)"
                    )

    print("Done.")
    print(f"ok={ok:,}, skip={skip:,}, 404={nf:,}, fail={fail:,}, other={other:,}")

if __name__ == "__main__":
    per_z, total = estimate_counts()
    print("=== Tile count estimate (XYZ) ===")
    for z in range(Z_MIN, Z_MAX + 1):
        nx, ny, cnt = per_z[z]
        print(f"z{z}: {nx} x {ny} = {cnt:,}")
    print(f"TOTAL: {total:,} tiles\n")

    run_download()