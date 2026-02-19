import numpy as np
from PIL import Image
from pathlib import Path

RAW_DIR = Path("raw_dem")
TERRA_DIR = Path("terrarium")

# 出力先
OUT_DIR = Path("diff_maps")

FOCUS_Z = 14              # まずは最大ズーム
TOP_N = 3                 # 最大誤差が大きいタイル上位N枚を出力
CLIP_M = 0.0020           # ヒートマップのクリップ幅（±m）。今回の誤差なら2mm程度が見やすい

GSI_NODATA_RGB = (128, 0, 0)

def load_rgb(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"), dtype=np.uint8)

def gsi_dem_to_height_m(rgb: np.ndarray):
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)

    h = (r * 256 * 256 + g * 256 + b).astype(np.float32) * 0.01
    h = np.where(r >= 128, h - 167772.16, h)

    nodata = (r == GSI_NODATA_RGB[0]) & (g == GSI_NODATA_RGB[1]) & (b == GSI_NODATA_RGB[2])
    return h, nodata

def terrarium_to_height_m(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    return (r * 256.0 + g + b / 256.0) - 32768.0

def diff_to_heat_rgb(diff: np.ndarray, valid: np.ndarray, clip_m: float) -> np.ndarray:
    """
    diff(m) をRGBヒートマップにする（簡易）
      - 正(terrariumが高い): 赤
      - 負(terrariumが低い): 青
      - 0付近: 黒
    """
    d = np.clip(diff, -clip_m, clip_m) / clip_m  # -1..1
    r = np.where(d > 0, (d * 255.0), 0.0)
    b = np.where(d < 0, (-d * 255.0), 0.0)
    g = np.zeros_like(r)

    out = np.stack([r, g, b], axis=-1).astype(np.uint8)

    # invalid(nodata) はグレー
    out[~valid] = np.array([128, 128, 128], dtype=np.uint8)
    return out

def write_legend_png(path: Path, clip_m: float):
    """
    256x32 の簡易凡例
      左=青(-clip) 右=赤(+clip)
    """
    w, h = 256, 32
    x = np.linspace(-1, 1, w, dtype=np.float32)
    r = np.where(x > 0, x * 255.0, 0.0)
    b = np.where(x < 0, -x * 255.0, 0.0)
    g = np.zeros_like(r)
    row = np.stack([r, g, b], axis=-1).astype(np.uint8)
    img = np.repeat(row[np.newaxis, :, :], h, axis=0)

    Image.fromarray(img, "RGB").save(path, format="PNG", optimize=True)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_legend_png(OUT_DIR / f"legend_clip_{CLIP_M}m.png", CLIP_M)

    z_dir = TERRA_DIR / str(FOCUS_Z)
    if z_dir.exists():
        terra_files = sorted(z_dir.rglob("*.png"))
    else:
        terra_files = sorted(TERRA_DIR.rglob("*.png"))

    if not terra_files:
        raise SystemExit("No terrarium png found.")

    stats = []

    # まず全タイルの max abs diff を計算してランキング
    for tpath in terra_files:
        rel = tpath.relative_to(TERRA_DIR)  # z/x/y.png
        rpath = RAW_DIR / rel
        if not rpath.exists():
            continue

        raw_rgb = load_rgb(rpath)
        ter_rgb = load_rgb(tpath)

        raw_h, raw_nodata = gsi_dem_to_height_m(raw_rgb)
        ter_h = terrarium_to_height_m(ter_rgb)

        valid = ~raw_nodata
        if not np.any(valid):
            continue

        diff = (ter_h - raw_h).astype(np.float32)
        max_abs = float(np.max(np.abs(diff[valid])))

        stats.append((max_abs, rel))

    if not stats:
        raise SystemExit("No comparable tiles found.")

    stats.sort(key=lambda x: x[0], reverse=True)
    pick = stats[:TOP_N]

    print(f"Writing heatmaps: top {TOP_N} tiles (focus z={FOCUS_Z} if exists)")
    for max_abs, rel in pick:
        tpath = TERRA_DIR / rel
        rpath = RAW_DIR / rel

        raw_rgb = load_rgb(rpath)
        ter_rgb = load_rgb(tpath)

        raw_h, raw_nodata = gsi_dem_to_height_m(raw_rgb)
        ter_h = terrarium_to_height_m(ter_rgb)

        valid = ~raw_nodata
        diff = (ter_h - raw_h).astype(np.float32)

        heat = diff_to_heat_rgb(diff, valid, CLIP_M)

        # 画像出力（ヒートマップ + diff数値の絶対値マップもオプションで）
        out_name = str(rel).replace("/", "_").replace("\\", "_").replace(".png", "")
        heat_path = OUT_DIR / f"{out_name}_diff_heat_clip{CLIP_M}m.png"
        Image.fromarray(heat, "RGB").save(heat_path, format="PNG", optimize=True)

        # 参考: diffの絶対値をグレースケール化（0..clip）
        absd = np.clip(np.abs(diff), 0, CLIP_M) / CLIP_M
        gray = (absd * 255.0).astype(np.uint8)
        gray_rgb = np.stack([gray, gray, gray], axis=-1)
        gray_path = OUT_DIR / f"{out_name}_absdiff_gray_clip{CLIP_M}m.png"
        Image.fromarray(gray_rgb, "RGB").save(gray_path, format="PNG", optimize=True)

        print(f"- {rel}  max_abs={max_abs:.6f} m")
        print(f"  {heat_path}")
        print(f"  {gray_path}")

    print(f"\nLegend: {OUT_DIR / f'legend_clip_{CLIP_M}m.png'}")
    print(f"Output dir: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
