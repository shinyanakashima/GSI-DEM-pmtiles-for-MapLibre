import numpy as np
from PIL import Image
from pathlib import Path

IN_DIR = Path("terrarium")  # terrarium/{z}/{x}/{y}.png
# どのズームを重点チェックするか（表示品質に効くので最大ズーム推奨）
FOCUS_Z = 14

def terrarium_to_height_m(rgb: np.ndarray) -> np.ndarray:
    """
    Terrarium RGB -> height in meters (float32)
      h = (R*256 + G + B/256) - 32768
    """
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    return (r * 256.0 + g + b / 256.0) - 32768.0

def main():
    if not IN_DIR.exists():
        raise SystemExit(f"Input dir not found: {IN_DIR.resolve()}")

    files = sorted(IN_DIR.rglob("*.png"))
    if not files:
        raise SystemExit("No PNG files found under terrarium/")

    # 任意：最大ズームだけに絞る（速くて実用的）
    z_dir = IN_DIR / str(FOCUS_Z)
    if z_dir.exists():
        files = sorted(z_dir.rglob("*.png"))

    global_min = float("inf")
    global_max = float("-inf")

    # nodata相当（今回の変換では nodata を 0m に落としているので 0mの比率を参考にする）
    zero_count = 0
    total_px = 0

    per_tile = []

    for p in files:
        img = Image.open(p).convert("RGB")
        rgb = np.array(img, dtype=np.uint8)
        h = terrarium_to_height_m(rgb)

        hmin = float(np.min(h))
        hmax = float(np.max(h))

        global_min = min(global_min, hmin)
        global_max = max(global_max, hmax)

        # 0mピクセル比率（nodataを0mにしてる場合は多すぎると要注意）
        zc = int(np.sum(h == 0.0))
        zero_count += zc
        total_px += h.size

        per_tile.append((str(p), hmin, hmax))

    print(f"Checked tiles: {len(files)} (focus z={FOCUS_Z} if exists)")
    print(f"Height min/max (m): {global_min:.3f} .. {global_max:.3f}")
    print(f"0m pixels ratio: {zero_count/total_px*100:.3f}%  (note: nodata->0mの場合は参考値)")

    # 代表としてmin/maxが極端なタイルを表示
    per_tile.sort(key=lambda x: x[1])  # minが低い順
    print("\n--- Lowest min tiles (top 3) ---")
    for t in per_tile[:3]:
        print(f"{t[0]}  min={t[1]:.3f}  max={t[2]:.3f}")

    per_tile.sort(key=lambda x: x[2], reverse=True)  # maxが高い順
    print("\n--- Highest max tiles (top 3) ---")
    for t in per_tile[:3]:
        print(f"{t[0]}  min={t[1]:.3f}  max={t[2]:.3f}")

if __name__ == "__main__":
    main()
