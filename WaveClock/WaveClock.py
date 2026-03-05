"""
WaveClock.py

Pico/Pico2シリーズを利用した電波時計のメインプログラム。
JJYの受信、デコード、RTCの補正、およびTM1637ディスプレイへの表示を一括して管理する。
"""
from Debug import Debug
from JJYDecoder import JJYDecoder
from JJYReceiver import JJYReceiver
from RTCClockApp import RTCClockApp
from tm1637 import TM1637
# 設定ファイル
from JJY_CONFIG import JJY_CONFIG

# 表示器
disp = TM1637(sda_pin=JJY_CONFIG["tm1637_sda_pin"],contrast=4)
# JJYデコーダー
jjy = JJYDecoder(smid=disp._available_ids.pop(),
                 input_port=JJY_CONFIG["signal_out_pin"],
                 input_pol=JJY_CONFIG["signal_pol"],
                 )

# JJY受信ユニット制御クラス
receiver = JJYReceiver(jjy,
                       pon_pin=JJY_CONFIG["pon_pin"],
                       pon_pol=JJY_CONFIG["pon_pol"],
                       band_sel_pin=JJY_CONFIG["band_select_pin"],
                       preferred_band=JJY_CONFIG["default_band"],
                       sync_indicator_pin=JJY_CONFIG["sync_indicator_pin"]
                       )

# 時計アプリケーションクラス
app = RTCClockApp(disp, jjy, receiver, 
                  mode_select_pin=JJY_CONFIG["mode_select_pin"],
                  force_sync_pin=JJY_CONFIG["force_sync_pin"])

# 時計スタート
app.run()
