import numpy as np
from PIL import Image
from pathlib import Path

# 入出力
IN_DIR = Path("raw_dem")
OUT_DIR = Path("terrarium")

# GSI dem_png の nodata（無効値）: RGB=(128,0,0)
NODATA_RGB = (128, 0, 0)

def gsi_dem_to_height_m(rgb: np.ndarray) -> np.ndarray:
    """
    GSI dem_png (RGB) -> height in meters (float32)
    rgb: HxWx3 uint8
    仕様:
      h = (R*256*256 + G*256 + B) * 0.01
      if R >= 128: h -= 167772.16
      nodata = (128,0,0)
    """
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)

    v = (r * 256 * 256 + g * 256 + b).astype(np.float32) * 0.01
    # 符号付き補正（R>=128）
    v = np.where(r >= 128, v - 167772.16, v)

    # nodata マスク
    nodata = (r == NODATA_RGB[0]) & (g == NODATA_RGB[1]) & (b == NODATA_RGB[2])
    return v, nodata

def height_m_to_terrarium_rgb(height_m: np.ndarray, nodata_mask: np.ndarray) -> np.ndarray:
    """
    height(m) -> Terrarium PNG RGB (uint8)
    Terrarium:
      v = h + 32768
      R = floor(v / 256)
      G = floor(v) % 256
      B = floor((v - floor(v)) * 256)
    nodata は 0m (v=32768) に落とす（見た目の破綻を抑える）
    """
    h = height_m.astype(np.float32)

    # nodata を 0m に置換（必要なら -32768 などに変えてもOK）
    h = np.where(nodata_mask, 0.0, h)

    v = h + 32768.0
    v_floor = np.floor(v)

    R = np.floor(v / 256.0).astype(np.int32)
    G = (v_floor.astype(np.int32) % 256)
    B = np.floor((v - v_floor) * 256.0).astype(np.int32)

    out = np.stack([R, G, B], axis=-1)

    # 範囲クリップ（安全策）
    out = np.clip(out, 0, 255).astype(np.uint8)
    return out

def convert_one(in_path: Path, out_path: Path):
    img = Image.open(in_path).convert("RGB")
    rgb = np.array(img, dtype=np.uint8)

    h_m, nodata = gsi_dem_to_height_m(rgb)
    out_rgb = height_m_to_terrarium_rgb(h_m, nodata)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out_rgb, mode="RGB").save(out_path, format="PNG", optimize=True)

def main():
    if not IN_DIR.exists():
        raise SystemExit(f"Input dir not found: {IN_DIR.resolve()}")

    files = list(IN_DIR.rglob("*.png"))
    if not files:
        raise SystemExit("No input PNG tiles found under raw_dem/")

    converted = 0
    for in_path in files:
        rel = in_path.relative_to(IN_DIR)  # z/x/y.png
        out_path = OUT_DIR / rel
        convert_one(in_path, out_path)
        converted += 1

    print(f"Converted: {converted} tiles")
    print(f"Output dir: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
