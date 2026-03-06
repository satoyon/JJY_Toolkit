from TimeSource import TimeSource
from TimeSyncer import TimeSyncer
from Debug import Debug
import utime as time
import network
import ntptime
from machine import Timer
from machine import Pin
from micropython import schedule

# Wi-Fi接続
def wifi_connect(ssid, passkey, timeout=20):
    conn = network.WLAN(network.STA_IF)
    if conn.isconnected():
        return conn
    conn.active(True)
    conn.connect(ssid, passkey)
    while not conn.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
    if conn.isconnected():
        return conn
    else:
        return None

class NTPSource(Debug, TimeSyncer, TimeSource):
    """NTP時刻ソース"""

    def __init__(self, ssid, passwd, sync_indicator_pin=18, sync_interval=120):
        """
        Args:
        sync_indicator_pin: 同期インジケーターのGPIO
        sync_interval: 同時間隔（分）
        """
        # Wi-Fi関連
        self.ssid = ssid        # SSID
        self.passwd = passwd    # パスフレーズ
        # 同期インジケーター
        self.sync_led = Pin(sync_indicator_pin, Pin.OUT)
        self.sync_led.value(0)      # 消灯
        # 同時間隔（デフォルト2時間）
        self.interval = sync_interval
        # タイマー1分
        self.tm = Timer()
        self.tm.init(mode=Timer.PERIODIC, period=60*1000, callback=self._timer_handler)
        # タイマーカウンタ
        self.tick_counter = self.interval + 1
        # コールバック関数
        self._callbacks = []
    
    def _timer_handler(self, t):
        self.tick_counter += 1
        if self.tick_counter > self.interval:   # 同時間隔
            self.tick_counter = 0   # カウンタリセット
            schedule(self.sync_start, 0)

    def sync_start(self, arg=0):
        # まずWi-Fi接続
        conn = wifi_connect(self.ssid, self.passwd)
        if conn is not None:
            conn.ifconfig()     # IP設定
            time.sleep(1)       # 安定するまで待つ
            ntptime.host = "ntp.nict.jp"
            now = ntptime.time() + 9 * 60 * 60  # 日本時間
            data = (now, time.ticks_ms())       # (UNIXエポックタイム, 受信ticks_ms)
            conn.active(False)      # 電源を切る
            self.sync_led.value(1)  # 同期LED点灯
            try:
                for callback in self._callbacks:
                    if callback is not None:
                        schedule(callback, data)
            except RuntimeError:
                self.dprint("--- schedule() queue full ---")
        else:
            self.dprint("--- Cant connect to %s", self.ssid)
    
    def sync_stop(self):
        """特にすることはなにもない"""
        return

    def add_callback(self, callback):
        """
        時刻を通知するコールバック関数
        """
        if callback is not None:
            self._callbacks.append(callback)
