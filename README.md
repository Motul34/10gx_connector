# toyopuc-10gx

JTEKT製PLC **TOYOPUC 10GX**（Nano 2ETモジュール等）と、PCからイーサネット（コンピュータリンク方式 TCP/IP）経由で通信を行うPythonライブラリです。

PyPIパッケージ名: **`toyopuc-10gx`**  
Pythonインポート名: **`import toyopuc`**

---

## 主な特徴

- **簡単接続**: `toyopuc.connect(ip, port)` で接続完了。
- **直感的なアドレス指定**: `"P1-M100"`, `"P2-D2000"`, `"P1-D100L"`, `"U0000"` などのアドレス文字列を自動で32ビット論理アドレス（Ex No.＋間接アドレス）に変換。
- **戻り値（リスト形式）**: 単一アドレスでも `[0]` で取得でき、複数アドレス（連番・飛び番・混在）も指定した順序のリストで一括取得可能。
- **全データ幅に対応**: ビット（1bit）、バイト（8bit）、ワード（16bit）、ロング（32bit）の読み書きを完備。
- **バックグラウンド定期監視（ポーラー機能）**: 別スレッドでの定期取得ループ・自動再接続・排他制御が可能。メインスレッドは通信待ち（ブロッキング）ゼロで最新値を参照。

---

## インストール

```bash
pip install toyopuc-10gx
```

---

## クイックスタート

### 1. 基本的な読み書き

```python
import toyopuc

# PLCに接続（デフォルトポート: 1025, タイムアウト: 3.0秒）
with toyopuc.connect("192.168.1.1", 1025) as plc:
    # --- ビットの読み書き ---
    # 単一書き込み（辞書形式）
    plc.bit_write({"P1-M100": 1})

    # 単一読み出し（戻り値はリストなので [0] で取得）
    m100 = plc.bit_read("P1-M100")[0]
    print(f"P1-M100: {m100}")  # -> 1

    # 複数ビットの一括読み出し（飛び番でもOK）
    vals = plc.bit_read("P1-M100", "P1-M108")
    print(vals)  # -> [1, 0]

    # 複数ビットの一括書き込み
    plc.bit_write({
        "P1-M100": 0,
        "P1-M108": 1,
        "P2-M200": 1,
    })

    # --- ワード（16bitレジスタ）の読み書き ---
    plc.word_write({
        "P1-D100": 1234,
        "P1-D205": 5678,
    })
    d100, d205 = plc.word_read("P1-D100", "P1-D205")
    print(f"D100: {d100}, D205: {d205}")

    # --- バイト（8bit）単位の読み書き ---
    plc.byte_write({"P1-D100L": 0x34, "P1-D100H": 0x12})
    byte_vals = plc.byte_read("P1-D100L", "P1-D100H")

    # --- ロング（32bit整数）の読み書き ---
    plc.long_write({"P1-D100": 100000})
    l_val = plc.long_read("P1-D100")[0]
```

---

### 2. バックグラウンド定期取得（スレッド監視・自動再接続）

PLCの特定アドレスをバックグラウンドスレッドで自動的に定期ポーリングし、最新値を常時保持します。
メインスレッドは通信待ち（フリーズ）することなく、いつでも瞬時に最新データを取得できます。

```python
import time
import toyopuc

plc = toyopuc.connect("192.168.1.1", 1025)

# バックグラウンド定期取得を開始（1秒間隔）
# 通信断が発生しても、バックグラウンドスレッドが自動で再接続をリトライします
poller = plc.start_polling(
    addresses=["P1-M100", "P1-M108", "P1-D100"],
    interval=1.0,
)

try:
    while True:
        # メイン処理側は待ち時間ゼロで最新値を取得可能
        m100 = poller.get("P1-M100")
        d100 = poller.get("P1-D100")
        all_data = poller.get_latest()  # 全アドレスの辞書を取得

        print(f"最新データ: M100={m100}, D100={d100}")

        # ポーリング稼働中でも、安全に書き込み可能（内部で排他ロック制御）
        if m100 == 1:
            plc.word_write({"P1-D100": 9999})

        time.sleep(1)
finally:
    # ポーリングの停止方法（以下のいずれでも可能）
    plc.stop_polling(poller)  # または poller.stop() または plc.stop_polling() で全停止
    plc.close()               # close() 時にすべてのポーラーも自動停止します
```

---

## 対応アドレス形式

取扱説明書（Nano 2ET 取扱説明書）のアドレス仕様および資料8（Exナンバー）に準拠しています。

| アドレス表記 | 対象デバイス | 備考 |
|---|---|---|
| `P1-M100` | プログラム1 内部リレー M100 | ビットデバイス（16進数指定） |
| `P2-K050` | プログラム2 キープリレー K050 | ビットデバイス |
| `P1-D100` | プログラム1 データレジスタ D100 | ワードデバイス（16ビット） |
| `P1-D100L` | プログラム1 データレジスタ D100 下位バイト | バイトデバイス（8ビット） |
| `P1-D100H` | プログラム1 データレジスタ D100 上位バイト | バイトデバイス（8ビット） |
| `D100` | プログラム指定省略時 | デフォルトでプログラム1（P1） |
| `P1-M1000` | PC10拡張 内部リレー M1000 | 拡張領域自動計算 |
| `U0000` | 拡張データレジスタ U0000 | Ex No. 0x03〜 |
| `EB0000` | 拡張ファイルレジスタ EB0000 | Ex No. 0x10〜 |
| `GM0000` | 拡張内部リレー GM0000 | Ex No. 0x02 |

---

## API リファレンス

### 接続関数
- `toyopuc.connect(ip: str, port: int = 1025, timeout: float = 3.0, auto_reconnect: bool = True) -> ToyopucClient`
  PLCとのTCPコネクションを確立し、`ToyopucClient` インスタンスを返します。

---

### `ToyopucClient` メソッド・プロパティ一覧

#### 読み出し系（戻り値は常に `list[int]`）
- `bit_read(*addresses) -> list[int]`: ビット読み出し（0 または 1 のリスト）
- `byte_read(*addresses) -> list[int]`: バイト読み出し（0〜255 のリスト）
- `word_read(*addresses) -> list[int]`: ワード読み出し（0〜65535 のリスト）
- `long_read(*addresses) -> list[int]`: ロング（32bit整数）読み出し（0〜4294967295 のリスト）
- `read_mixed(addresses: Sequence[str]) -> dict[str, int]`: ビット・バイト・ワード混在一括読み出し（辞書返却）

#### 書き込み系（引数は辞書形式 `{"アドレス": 値}`）
- `bit_write(data, value=None) -> int`: ビット書き込み（書き込み件数を返却）
- `byte_write(data, value=None) -> int`: バイト書き込み（書き込み件数を返却）
- `word_write(data, value=None) -> int`: ワード書き込み（書き込み件数を返却）
- `long_write(data, value=None) -> int`: ロング（32bit整数）書き込み（書き込み件数を返却）

#### ポーリング制御
- `start_polling(addresses: Sequence[str], interval: float = 1.0) -> BackgroundPoller`: バックグラウンド定期取得を開始
- `stop_polling(poller: BackgroundPoller | None = None) -> None`: 指定したポーラー（または全ポーラー）を停止

#### コネクション管理
- `connect() -> ToyopucClient`: 再接続を実行
- `disconnect() -> None`: ソケット切断（`close()` のエイリアス）
- `close() -> None`: 全ポーラーを停止し、ソケットを切断
- `is_connected -> bool`: 現在ソケットが接続中かどうか

---

### `BackgroundPoller` メソッド・プロパティ一覧

- `get(address: str, default: Any = None) -> int | None`: 指定アドレスの最新キャッシュ値を即座に取得
- `get_latest() -> dict[str, int]`: 全監視アドレスの最新データ辞書のコピーを取得
- `stop(timeout: float = 3.0) -> None`: ポーリングスレッドを停止
- `start() -> None`: 停止中のポーリングスレッドを再開
- `set_addresses(addresses: Sequence[str]) -> None`: 監視対象アドレスリストを動的に変更
- `set_interval(interval: float) -> None`: ポーリング間隔（秒）を動的に変更
- `is_running -> bool`: ポーリングスレッドが稼働中かどうか
- `last_error -> Exception | None`: 直近に発生した通信エラー（正常時は `None`）

---

## ライセンス

MIT License
