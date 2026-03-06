"""
NTPClock.py

Pico W/Pico2 Wを利用したNTP時計のメインプログラム。
"""
from Debug import Debug
from NTPSource import NTPSource
from RTCClockApp import RTCClockApp
from tm1637 import TM1637
# 設定ファイル
from NTP_CONFIG import NTP_CONFIG

# 表示器
disp = TM1637(sda_pin=NTP_CONFIG["tm1637_sda_pin"],contrast=4)
# NTP時刻ソース
ntp = NTPSource(NTP_CONFIG["ssid"], NTP_CONFIG["pass"],sync_indicator_pin=NTP_CONFIG["sync_indicator_pin"])

# 時計アプリケーションクラス
app = RTCClockApp(disp, ntp, ntp, 
                  mode_select_pin=NTP_CONFIG["mode_select_pin"],
                  force_sync_pin=NTP_CONFIG["force_sync_pin"])

# 時計スタート
app.run()
# 終了処理
disp.release()
