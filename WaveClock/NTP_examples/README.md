# おまけ～NTPサンプル

`TimeSource`/`TimeSyncer`の実装例として、NTPを日時ソースとして使うサンプルを用意しました。このソースはWi-Fi接続ができるPico WおよびPico 2 W用で、Wi-FiがないPico/Pico 2では利用できません。

## NTP時計の使い方

まず、次のような`NTP_CONFIG.py` を環境に合わせて作成してください。

```python
NTP_CONFIG = {
    "ssid": "your_wifi_ssid",       # 接続するアクセスポイント名
    "pass": "your_accesspass",      # 接続パスワード
    "tm1637_sda_pin": 2,            # TM1637モジュールのDIO（SDA）が接続されているGPIO
    "sync_indicator_pin": 18,       # 強制同期スイッチのGPIO
    "mode_select_pin": 16,          # 表示モード切替スイッチのGPIO
    "force_sync_pin": 17,           # 同期インジケーターLEDのGPIO
}
```

このディレクトリにある2つのソースと、１つ上のディレクトリにある次のソースを合わせてPico W/Pico 2 Wにアップロードします。

* RTCClockApp.py: 時計アプリクラス
* NTPSource.py: NTP時刻ソース
* TimeSource.py: 基底クラスTimeSource
* TimeSyncer.py: 基底クラスTimeSyncer
* NTPClock.py: メインプログラム
* NTP_CONFIG.py: 設定ファイル（上記）
* tm1637.py: TM1637ライブラリ

NTPClock.pyを実行します。少し待つとTM1637のLEDディスプレイに時刻が表示されるでしょう。デフォルトでは120分おきにNTPに接続してRTCの補正を行います。
