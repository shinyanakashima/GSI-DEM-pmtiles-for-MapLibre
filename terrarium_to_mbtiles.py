import sqlite3
from pathlib import Path

# ===== 入出力 =====
IN_DIR = Path("terrarium")                 # terrarium/{z}/{x}/{y}.png
OUT_MB = Path("dem_terrarium_z8-14.mbtiles")

# ===== メタ情報（bbox固定）=====
BOUNDS_W, BOUNDS_S, BOUNDS_E, BOUNDS_N = (
    144.124997317805,
    43.8750031560014,
    144.249993622593,
    43.9583319289041,
)
MINZOOM = 8
MAXZOOM = 14

def xyz_y_to_tms_y(z: int, y_xyz: int) -> int:
    # MBTiles tiles.tile_row は TMS（XYZからy反転）
    return (2 ** z - 1 - y_xyz)

def ensure_schema(cur: sqlite3.Cursor):
    cur.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;

    CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT);
    CREATE TABLE IF NOT EXISTS tiles (
        zoom_level INTEGER,
        tile_column INTEGER,
        tile_row INTEGER,
        tile_data BLOB
    );
    CREATE UNIQUE INDEX IF NOT EXISTS tile_index
      ON tiles (zoom_level, tile_column, tile_row);
    """)

def upsert_metadata(cur: sqlite3.Cursor, name: str, value: str):
    cur.execute("DELETE FROM metadata WHERE name = ?", (name,))
    cur.execute("INSERT INTO metadata(name, value) VALUES(?, ?)", (name, value))

def parse_zxy(p: Path):
    # terrarium/z/x/y.png
    rel = p.relative_to(IN_DIR)
    if len(rel.parts) < 3:
        raise ValueError(f"Unexpected path: {p}")
    z = int(rel.parts[0])
    x = int(rel.parts[1])
    y = int(rel.parts[2].replace(".png", ""))
    return z, x, y

def main():
    if not IN_DIR.exists():
        raise SystemExit(f"Input dir not found: {IN_DIR.resolve()}")

    files = sorted(IN_DIR.rglob("*.png"))
    if not files:
        raise SystemExit("No PNG files found under terrarium/")

    if OUT_MB.exists():
        OUT_MB.unlink()

    conn = sqlite3.connect(str(OUT_MB))
    try:
        cur = conn.cursor()
        ensure_schema(cur)

        # ---- metadata（最低限 + 使えるもの）----
        upsert_metadata(cur, "name", "GSI DEM (Terrarium) z8-14")
        upsert_metadata(cur, "format", "png")
        upsert_metadata(cur, "minzoom", str(MINZOOM))
        upsert_metadata(cur, "maxzoom", str(MAXZOOM))
        upsert_metadata(cur, "bounds", f"{BOUNDS_W},{BOUNDS_S},{BOUNDS_E},{BOUNDS_N}")
        upsert_metadata(cur, "type", "overlay")
        upsert_metadata(cur, "description", "Converted from GSI dem_png to Terrarium encoding for MapLibre raster-dem.")
        conn.commit()

        inserted = 0
        skipped = 0

        cur.execute("BEGIN;")
        for p in files:
            z, x, y = parse_zxy(p)
            if z < MINZOOM or z > MAXZOOM:
                skipped += 1
                continue

            tile_row = xyz_y_to_tms_y(z, y)
            data = p.read_bytes()

            cur.execute(
                "INSERT OR REPLACE INTO tiles(zoom_level, tile_column, tile_row, tile_data) VALUES(?,?,?,?)",
                (z, x, tile_row, sqlite3.Binary(data)),
            )
            inserted += 1

            if inserted % 1000 == 0:
                print(f"Inserted {inserted} tiles...")

        conn.commit()

        # 統計/最適化
        cur.execute("ANALYZE;")
        conn.commit()

        print(f"MBTiles written: {OUT_MB.resolve()}")
        print(f"Tiles inserted: {inserted}")
        if skipped:
            print(f"Tiles skipped (outside z range): {skipped}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
