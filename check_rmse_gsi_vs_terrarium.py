import numpy as np
from PIL import Image
from pathlib import Path

RAW_DIR = Path("raw_dem")       # GSI dem_png: raw_dem/{z}/{x}/{y}.png
TERRA_DIR = Path("terrarium")   # Terrarium:  terrarium/{z}/{x}/{y}.png
FOCUS_Z = 14                    # まずは最大ズーム推奨（存在しなければ全体）

# GSI dem_png nodata（無効値）
GSI_NODATA_RGB = (128, 0, 0)

def gsi_dem_to_height_m(rgb: np.ndarray):
    """
    GSI dem_png (RGB uint8) -> (height_m float32, nodata_mask bool)
    h = (R*256*256 + G*256 + B)*0.01
    if R>=128: h -= 167772.16
    nodata = (128,0,0)
    """
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)

    h = (r * 256 * 256 + g * 256 + b).astype(np.float32) * 0.01
    h = np.where(r >= 128, h - 167772.16, h)

    nodata = (r == GSI_NODATA_RGB[0]) & (g == GSI_NODATA_RGB[1]) & (b == GSI_NODATA_RGB[2])
    return h, nodata

def terrarium_to_height_m(rgb: np.ndarray) -> np.ndarray:
    """
    Terrarium RGB -> height(m)
    h = (R*256 + G + B/256) - 32768
    """
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    return (r * 256.0 + g + b / 256.0) - 32768.0

def load_rgb(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"), dtype=np.uint8)

def main():
    if not RAW_DIR.exists():
        raise SystemExit(f"raw_dem not found: {RAW_DIR.resolve()}")
    if not TERRA_DIR.exists():
        raise SystemExit(f"terrarium not found: {TERRA_DIR.resolve()}")

    # 比較対象タイル一覧（Terrarium側を基準にペアを作る）
    terra_files = sorted(TERRA_DIR.rglob("*.png"))
    if not terra_files:
        raise SystemExit("No terrarium png found.")

    # 最大ズームだけに絞る（存在するなら）
    z_dir = TERRA_DIR / str(FOCUS_Z)
    if z_dir.exists():
        terra_files = sorted(z_dir.rglob("*.png"))

    sum_sq = 0.0
    sum_abs = 0.0
    n = 0
    max_abs = 0.0
    max_abs_tile = None

    # 参考：タイルごとの統計も少し出す
    per_tile_stats = []

    for tpath in terra_files:
        rel = tpath.relative_to(TERRA_DIR)   # z/x/y.png
        rpath = RAW_DIR / rel
        if not rpath.exists():
            # raw_demが無いタイルはスキップ（通常無いはず）
            continue

        raw_rgb = load_rgb(rpath)
        ter_rgb = load_rgb(tpath)

        if raw_rgb.shape != ter_rgb.shape:
            raise RuntimeError(f"Tile size mismatch: {rel} raw={raw_rgb.shape} terra={ter_rgb.shape}")

        raw_h, raw_nodata = gsi_dem_to_height_m(raw_rgb)
        ter_h = terrarium_to_height_m(ter_rgb)

        # nodataは評価から除外（trueなところは無視）
        valid = ~raw_nodata
        if not np.any(valid):
            continue

        diff = (ter_h[valid] - raw_h[valid]).astype(np.float64)
        absdiff = np.abs(diff)

        tile_n = diff.size
        tile_rmse = float(np.sqrt(np.mean(diff * diff)))
        tile_mae = float(np.mean(absdiff))
        tile_max = float(np.max(absdiff))

        per_tile_stats.append((str(rel).replace("\\", "/"), tile_n, tile_rmse, tile_mae, tile_max))

        sum_sq += float(np.sum(diff * diff))
        sum_abs += float(np.sum(absdiff))
        n += tile_n

        if tile_max > max_abs:
            max_abs = tile_max
            max_abs_tile = str(rel).replace("\\", "/")

    if n == 0:
        raise SystemExit("No valid pixels to compare (all nodata?)")

    rmse = np.sqrt(sum_sq / n)
    mae = sum_abs / n

    print(f"Compared tiles: {len(per_tile_stats)} (focus z={FOCUS_Z} if exists)")
    print(f"Valid pixels: {n:,}")
    print(f"RMSE (m): {rmse:.6f}")
    print(f"MAE  (m): {mae:.6f}")
    print(f"Max abs error (m): {max_abs:.6f}  at tile {max_abs_tile}")

    # 代表として誤差が大きいタイルTOP3
    per_tile_stats.sort(key=lambda x: x[4], reverse=True)
    print("\n--- Worst tiles by max abs error (top 3) ---")
    for rel, tile_n, tile_rmse, tile_mae, tile_max in per_tile_stats[:3]:
        print(f"{rel}  n={tile_n:,}  rmse={tile_rmse:.6f}  mae={tile_mae:.6f}  max={tile_max:.6f}")

if __name__ == "__main__":
    main()
