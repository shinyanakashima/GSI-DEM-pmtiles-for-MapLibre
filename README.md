# 地形データのオフライン化
GSIのdem_pngをpmtiles化し、オフラインでも動作するようpmtilesにする。

1. GSIタイル（dem_png）を取得
2. Terrarium変換
3. MBTiles化
4. PMTiles化

## 1.GSIタイル（dem_png）を取得
DEMの元データ（5m/10m）から直接メッシュ生成するよりも確実。
仮想環境の作成し、依存ライブラリをインストールする。
```shell
python -m venv .venv
.\.venv\Scripts\Activate
pip install requests
```
実行
```shell
python dem_png.py
```

## 2.Terrarium変換
GSIの`dem_png`([raw_dem/{z}/{x}/{y}.png](raw_dem/))を `Terrarium PNG` に変換して[terrarium/{z}/{x}/{y}.png](terrarium/) に出力する。

実行
```shell
python .\to_terrarium.py
```

### ✅1.min/max を出す簡易チェック
Terrarium→標高に戻して min/max を出す簡易チェック。

実行
```shell
python check_terrarium.py
```

#### 見方（正常/異常の目安）
- OK: min/max が 現実的な範囲（例：-500〜4000mくらい）
- NG(encoding/復号ミス): min が -30000m 付近や max が +30000m 付近
- NG(nodata処理が0mに偏ってる): 0m pixels ratio が異常に高
  - 例：50%超。nodataは周辺補間に変えることを検討

### ✅2.RMSE
GSI dem_png → Terrarium → 復号して元標高との差分を求める。
元のGSI dem_png と 生成したTerrarium を同一タイルで突き合わせて、ピクセル単位の RMSE / MAE / 最大誤差 を出す。

実行
```shell
python check_rmse_gsi_vs_terrarium.py
```

#### 見方（正常/異常の目安）
- 「GSI→float→Terrarium(8bit+1/256)」なので、誤差は基本 量子化分だけで、RMSE はだいたい 0.01～0.05m 程度（タイル/地形次第）
- Max abs も 0.01～0.1m 程度が目安です。もし 数m〜数万m 出たら encoding/復号のバグの可能性

##### 例：
理想的な状態。RMSE 1mm台、最大誤差 1.9mmは **量子化誤差（TerrariumのBが1/256m刻み）**の範囲に収まっていて、変換は正しくできている。

実行
```shell
$ python check_rmse_gsi_vs_terrarium.py

Compared tiles: 36 (focus z=14 if exists)
Valid pixels: 2,359,296
RMSE (m): 0.001009
MAE  (m): 0.000800
Max abs error (m): 0.001877  at tile 14/14751/5960.png

--- Worst tiles by max abs error (top 3) ---
14/14751/5960.png  n=65,536  rmse=0.000850  mae=0.000583  max=0.001877
14/14751/5961.png  n=65,536  rmse=0.000882  mae=0.000607  max=0.001877
14/14751/5965.png  n=65,536  rmse=0.001100  mae=0.000952  max=0.001877
```

### ✅3.誤差の diffヒートマップPNGで可視化
誤差の diffヒートマップPNG を書き出す。「最大誤差が出たタイル」＋任意で上位N枚を表示する。

#### output
- diff_maps/legend_clip_0.002m.png
- diff_maps/14_14751_5960_diff_heat_clip0.002m.png など（TOP_N枚）
- diff_maps/..._absdiff_gray_clip0.002m.png

実行
```shell
python write_diff_heatmaps.py
```

#### 見方（正常/異常の目安）
- 赤：Terrariumの方が高い（+誤差）
- 青：Terrariumの方が低い（-誤差）
- 灰：GSI nodata（評価除外）
- 今回の誤差はmmなので、ほぼ「ランダムな微小差」に見えるのが正常

##### 例：
今回の誤差は 最大でも 0.001877m（約1.9mm） なので、ヒートマップは「うっすら赤青」か、ほぼ黒に近いはず（正常）

```shell
python .\check_write_diff_heatmaps.py
Writing heatmaps: top 3 tiles (focus z=14 if exists)
- 14\14751\5960.png  max_abs=0.001877 m
  diff_maps\14_14751_5960_diff_heat_clip0.002m.png
  diff_maps\14_14751_5960_absdiff_gray_clip0.002m.png
- 14\14751\5961.png  max_abs=0.001877 m
  diff_maps\14_14751_5961_diff_heat_clip0.002m.png
  diff_maps\14_14751_5961_absdiff_gray_clip0.002m.png
- 14\14751\5965.png  max_abs=0.001877 m
  diff_maps\14_14751_5965_diff_heat_clip0.002m.png
  diff_maps\14_14751_5965_absdiff_gray_clip0.002m.png

Legend: diff_maps\legend_clip_0.002m.png
Output dir: xxxx\bg_satelite\Terrain\diff_maps
```

## 3.terrarium(ディレクトリ)をMBTilesにする
terrarium/{z}/{x}/{y}.png を読み、MBTiles（SQLite） に投入する。MBTilesはTMSなので y反転する。

実行
```shell
python terrarium_to_mbtiles.py
```

##### 例：
61タイル挿入＝期待どおり（raw_dem/terrarium の総数と一致）なので、MBTiles化は成功。

```shell
python terrarium_to_mbtiles.py
MBTiles written: xxxx\bg_satelite\Terrain\dem_terrarium_z8-14.mbtiles
Tiles inserted: 61
```

## 4.pmtiles化

実行
```shell
pmtiles convert dem_terrarium_z8-14.mbtiles dem_terrarium_z8-14.pmtiles
```

確認
```shell
pmtiles verify dem_terrarium_z8-14.pmtiles
```

##### 例：
convert/verify ともに成功。

```shell
pmtiles convert dem_terrarium_z8-14.mbtiles dem_terrarium_z8-14.pmtiles
2026/02/19 16:24:53 convert.go:159: Pass 1: Assembling TileID set
2026/02/19 16:24:53 convert.go:190: Pass 2: writing tiles
 100% |██████████████████████████████████████████████████████████████████████████████████████████████████████████████| (61/61, 4437 it/s)         
2026/02/19 16:24:53 convert.go:244: # of addressed tiles:  61
2026/02/19 16:24:53 convert.go:245: # of tile entries (after RLE):  61
2026/02/19 16:24:53 convert.go:246: # of tile contents:  61
2026/02/19 16:24:53 convert.go:269: Total dir bytes:  271
2026/02/19 16:24:53 convert.go:270: Average bytes per addressed tile: 4.44
2026/02/19 16:24:53 convert.go:239: Finished in  39.6865ms
```

```shell
pmtiles verify dem_terrarium_z8-14.pmtiles
Completed verify in 520.5µs.
```

