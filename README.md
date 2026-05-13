# 📷 HLI 商品画像後処理ツール (Phase 1 / v1)

ECサイト「HLI」の商品画像を、カテゴリ別ルールで **クロップ → リサイズ → WebP変換 → サイズバッジ付与 → Dropbox 規定フォルダ保存** まで一括処理する Python CLI ツール。

## 🚀 セットアップ

```powershell
# 1. 依存ライブラリをインストール
pip install -r requirements.txt
```

## 🌐 Web UI（推奨：ブラウザから操作）

```powershell
streamlit run streamlit_app.py
```

ブラウザが自動で `http://localhost:8501` を開きます。画像とCSVをドラッグ＆ドロップで投入し、カテゴリ・シリーズ名を選んで「処理開始」を押すと、サムネイルプレビュー付きで結果が表示され、ZIP でダウンロードできます。CLI 版（後述）と同じ `process_one_image()` を内部で呼んでいるので挙動は完全に一致します。Dropbox には書き込みません。

## 🧪 サンプル画像で動作確認

Dropbox を経由せずローカルに出力して、まず動かしてみる手順。

```powershell
# 2. テスト用 3:2 画像を input/ に3枚生成
python generate_samples.py

# 3. ローカル ./out に出力するモードで実行
python process.py --output-base .\out
```

実行すると対話画面が出るので：

```
カテゴリを選んでください:
   1. 01_リネン            🏷️バッジあり
   2. 02_ウェア
   ...
> 1                              ← 01_リネン を選択

シリーズ名を入力してください（例: 2025春コレクション）:
> テスト2025春                    ← 任意の名前
```

`out\01_リネン\テスト2025春\` 配下に以下が生成されます：

```
out\01_リネン\テスト2025春\
├─ 高画質（印刷用・バナー作成用）\  ITEM001.jpg / ITEM002.jpg / ITEM003.jpg
├─ サムネイル\                    ITEM00X.webp  ← ITEM001/002/003 にバッジが付く
├─ 1200×1800\                    ITEM00X.webp
├─ 1200×1200\                    ITEM00X.webp
├─ スライダー用\PC\                ITEM00X.webp
├─ スライダー用\スマホ\             ITEM00X.webp
└─ psd\                          （空フォルダ）
```

## 🖥 本番運用（Dropbox 出力）

```powershell
# 入力画像を input/ に配置（JPG/PNG、3:2 横、ファイル名 = 商品ID）
# size_list.csv に該当商品IDとサイズコードを記入

python process.py
```

`--output-base` を省略すると `~/Dropbox/03_HLIデザイン/03_素材写真/■商品カテゴリ/` に出力します。Dropbox が無い場合は警告して、作成して続行するか確認されます。

## 📂 ファイル構成

| ファイル | 内容 |
|---|---|
| `process.py` | メインスクリプト（CLI・全体フロー） |
| `utils.py` | クロップ／バッジ／フォント検出などのユーティリティ |
| `generate_samples.py` | 動作確認用 3:2 サンプル画像3枚を `input/` に生成 |
| `size_list.csv` | 商品リスト：{商品ID, 新ファイル名, サイズコード}（リネームとバッジを制御） |
| `requirements.txt` | 依存ライブラリ（Pillow, tqdm） |
| `input/` | 入力画像を置く場所 |
| `samples/` | サンプル CSV |
| `error_log.txt` | 実行時に自動生成 |
| `SPEC.md` | 仕様書 |

## ⚙️ コマンドラインオプション

```
python process.py [--input-dir DIR] [--size-list CSV]
                  [--output-base DIR] [--error-log FILE]
```

| オプション | 既定 | 説明 |
|---|---|---|
| `--input-dir`    | `input` | 入力画像フォルダ |
| `--size-list`    | `size_list.csv` | サイズリスト CSV |
| `--output-base`  | Dropbox 規定パス | テスト時はローカルパスを指定 |
| `--error-log`    | `error_log.txt` | エラーログ出力先 |

## 🏷️ サイズバッジが付く条件

**3つすべて満たすときだけ** バッジが描画されます：

1. カテゴリが `01_リネン` / `11_シモンズ` / `12_シルク真綿布団` / `13_ダウン・フェザー製品` / `14_ブランケット`
2. `size_list.csv` に該当商品ID がある
3. 出力が **1200×1200 のサムネイル** （他サイズ・他カテゴリには付かない）

## 🪚 クロップ方針

| カテゴリ群 | クロップ中心 |
|---|---|
| 左カット群（01/11/12/13） | 中心を **右に15%シフト**（左側がカットされる）|
| 中央クロップ群（上記以外） | 画像中央 |

出力比率がワイド（1922×824）の場合は上下カット、それ以外は左右カットになります。

## 🛠 トラブルシューティング

| 症状 | 対処 |
|---|---|
| `セリフ系フォントが見つかりません` | Yu Mincho / ヒラギノ明朝 / Noto Serif CJK をインストール、または `utils.py` の `_FONT_CANDIDATES_SERIF` にパスを追記 |
| `Dropbox の規定パスが見つかりません` | パスを作成して続行（プロンプトで `y`）／テストなら `--output-base .\out` |
| `入力画像が見つかりません` | `input/` に JPG/PNG を置く、または `python generate_samples.py` を先に実行 |
| 元画像が縦長 | 横方向クロップは縮退するが落ちはしない。3:2 横を推奨 |

エラー時は `error_log.txt` に画像IDと例外を追記し、その画像はスキップして処理続行します。

## 🗺 今後（Phase 2）

`ANTHROPIC_API_KEY` と Claude Vision API を使い、画像ごとの最適クロップ位置を判定する機能を別途追加予定。v1 安定後に着手。
