# toyopuc-10gx

JTEKT製PLC（TOYOPUC 10GX / Nano 2ET等）とイーサネット（コンピュータリンク方式 TCP/IP）経由で通信するためのPythonライブラリです。

## 特徴

- Python標準ライブラリのみで動作（外部依存パッケージなし）
- ビット（1bit）、バイト（8bit）、ワード（16bit）、ロング（32bit）の読み書きに対応
- `P1-M100`、`P2-D2000`、`U0000` などのアドレス表記を自動で32bit論理アドレスに変換
- 複数アドレスの一括読み書きに対応（コマンド上限127点を超える場合は自動で分割送信）
- 別スレッドによる定期ポーリングと自動再接続

## 動作要件

- Python 3.8 以上

## インストール

```bash
pip install toyopuc-10gx
```

## 基本的な使い方

### 接続と読み書き

```python
import toyopuc

# PLCに接続（デフォルトポート: 1025, タイムアウト: 3.0秒）
with toyopuc.connect("192.168.1.1", 1025) as plc:
    # ビットの読み書き
    plc.bit_write("P1-M100", 1)
    m100 = plc.bit_read("P1-M100")[0]  # 戻り値は常に list[int]
    print(f"M100: {m100}")

    # 複数ビットの一括読み書き（連番・飛び番問わず指定可能）
    plc.bit_write({"P1-M100": 0, "P1-M108": 1})
    m100, m108 = plc.bit_read("P1-M100", "P1-M108")

    # ワード（16bit）の読み書き
    plc.word_write("P1-D100", 1234)
    d100 = plc.word_read("P1-D100")[0]

    # 複数ワードの一括読み出し
    d100, d205 = plc.word_read("P1-D100", "P1-D205")

    # バイト（8bit）の読み書き（下位バイト: L, 上位バイト: H）
    plc.byte_write({"P1-D100L": 0x34, "P1-D100H": 0x12})
    d100l, d100h = plc.byte_read("P1-D100L", "P1-D100H")

    # ロング（32bit整数）の読み書き
    plc.long_write("P1-D100", 100000)
    l_val = plc.long_read("P1-D100")[0]

    # ビット・ワード混在の一括読み出し（辞書形式で取得）
    data = plc.read_mixed(["P1-M100", "P1-D100"])
    # -> {"P1-M100": 0, "P1-D100": 100000 & 0xFFFF}
```

### バックグラウンド定期ポーリング

指定したアドレス群を別スレッドで定期監視し、キャッシュから最新値を参照します。ポーリング稼働中も同一接続インスタンスから安全に書き込みが可能です（内部で排他ロック制御されます）。

```python
import time
import toyopuc

plc = toyopuc.connect("192.168.1.1", 1025)

# 1.0秒間隔でバックグラウンド取得を開始
poller = plc.start_polling(
    addresses=["P1-M100", "P1-D100"],
    interval=1.0,
)

try:
    while True:
        # キャッシュから最新値を取得
        m100 = poller.get("P1-M100")
        d100 = poller.get("P1-D100")
        print(f"M100: {m100}, D100: {d100}")

        # ポーリング中も通常通り書き込み可能
        if m100 == 1:
            plc.word_write("P1-D100", 9999)

        time.sleep(1)
finally:
    plc.close()  # close() 時にポーリングスレッドも停止
```

## アドレスの指定記法

アドレス文字列は TOYOPUC の表記規則に準拠しています。

- **書式**: `[プログラム番号-]デバイス記号アドレス番号[バイト指定]`
  - **プログラム番号**（省略時は `P1`）: `P1-` / `P2-` / `P3-`
  - **アドレス番号**: **16進数** で指定します（例: `D100` は 10進数の 256 に相当）
  - **バイト指定**（任意）: 下位バイト `L`、上位バイト `H`

### 主な対応デバイス

| 種別 | デバイス記号 | 説明 |
| :--- | :--- | :--- |
| **基本ビット** | `P`, `K`, `V`, `TC`, `T`, `C`, `L`, `X`, `Y`, `M` | 入出力リレー、内部リレー、タイマ/カウンタ接点など |
| **拡張ビット** | `EP`, `EK`, `EV`, `ETC`, `ET`, `EC`, `EL`, `EX`, `EY`, `EM`, `GX`, `GY`, `GM` | 拡張リレー、拡張タイマ/カウンタ接点 |
| **基本ワード** | `D`, `B`, `S`, `N`, `R` | データレジスタ、ファイルレジスタ、特殊/現在値レジスタ |
| **拡張ワード** | `U`, `EB`, `ES`, `EN`, `H` | 拡張データレジスタ、拡張バッファレジスタ、設定値レジスタ |


## エラーハンドリング

通信障害やPLC側の異常応答は、`toyopuc.exceptions` 配下の例外として送出されます。

```python
import toyopuc
from toyopuc.exceptions import (
    ToyopucConnectionError,
    ToyopucResponseError,
    ToyopucAddressError,
)

try:
    with toyopuc.connect("192.168.1.1", 1025, timeout=3.0) as plc:
        plc.word_write("P1-D100", 1234)
except ToyopucConnectionError as e:
    # 接続失敗、タイムアウト、通信切断
    print(f"通信エラー: {e}")
except ToyopucResponseError as e:
    # PLCからの異常応答（アドレス範囲外、書き込み禁止など）
    print(f"PLCエラー応答: {e} (RC=0x{e.response_code:02X})")
except ToyopucAddressError as e:
    # 不正なアドレス形式
    print(f"アドレス指定エラー: {e}")
```

## APIリファレンス

### `toyopuc.connect()`
```python
toyopuc.connect(
    ip: str,
    port: int = 1025,
    timeout: float = 3.0,
    auto_reconnect: bool = True
) -> ToyopucClient
```
PLCにTCP接続し、`ToyopucClient` のインスタンスを返します。

### `ToyopucClient`
PLCとの通信を管理するクライアントクラスです。

#### 読み出しメソッド
| メソッド | 引数 | 戻り値 | 説明 |
| :--- | :--- | :--- | :--- |
| `bit_read(*addresses)` | 可変長引数またはリスト | `list[int]` | ビット読み出し（0 または 1） |
| `byte_read(*addresses)` | 可変長引数またはリスト | `list[int]` | バイト読み出し（0〜255） |
| `word_read(*addresses)` | 可変長引数またはリスト | `list[int]` | ワード読み出し（0〜65535） |
| `long_read(*addresses)` | 可変長引数またはリスト | `list[int]` | 32bit整数読み出し（0〜4294967295） |
| `read_mixed(addresses)` | `Sequence[str]` | `dict[str, int]` | ビット・ワード混在読み出し |

※読み出しメソッドの戻り値は、指定アドレス順の値リストです。単一アドレスの場合は `[0]` で値を取得します。

#### 書き込みメソッド
各メソッドとも、単一引数 `(address, value)` または辞書形式 `{"address": value, ...}` の両方に対応しています。

| メソッド | 引数 | 戻り値 | 説明 |
| :--- | :--- | :--- | :--- |
| `bit_write(data, value=None)` | `dict` または `(str, int\|bool)` | `int` | ビット書き込み（書き込み点数を返却） |
| `byte_write(data, value=None)` | `dict` または `(str, int)` | `int` | バイト書き込み |
| `word_write(data, value=None)` | `dict` または `(str, int)` | `int` | ワード書き込み |
| `long_write(data, value=None)` | `dict` または `(str, int)` | `int` | 32bit整数書き込み |

#### ポーリング・接続制御
| メソッド / プロパティ | 説明 |
| :--- | :--- |
| `start_polling(addresses, interval=1.0)` | バックグラウンド定期取得を開始し、`BackgroundPoller` を返却 |
| `stop_polling(poller=None)` | 指定したポーラー（省略時は全ポーラー）を停止 |
| `is_connected` | ソケットの接続状態（`bool`） |
| `connect()` | 再接続を実行 |
| `close()` / `disconnect()` | 全ポーラーを停止し、ソケットを切断 |

### `BackgroundPoller`
バックグラウンド定期ポーリングを制御・参照するクラスです。

| メソッド / プロパティ | 説明 |
| :--- | :--- |
| `get(address, default=None)` | 指定アドレスの最新値を取得 |
| `get_latest()` | 全対象アドレスの最新値を辞書形式で取得 |
| `start()` / `stop(timeout=3.0)` | ポーリングスレッドの再開 / 停止 |
| `set_addresses(addresses)` | 対象アドレスリストを変更 |
| `set_interval(interval)` | ポーリング間隔（秒）を変更 |
| `is_running` | ポーリングスレッドの稼働状態（`bool`） |
| `last_error` | 直近で発生した例外オブジェクト（正常時は `None`） |

## ライセンス

MIT License
