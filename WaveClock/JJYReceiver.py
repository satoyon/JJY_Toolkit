from Debug import Debug
from machine import Pin
from machine import RTC
import utime as time
from JJYDecoder import JJYDecoder
from micropython import schedule
from machine import Timer
from TimeSyncer import TimeSyncer

# 定数定義
STATE_IDLE  = 0
STATE_TRY   = 1
STATE_RETRY = 2

class JJYReceiver(Debug,TimeSyncer):

    def __init__(self, jjydec: JJYDecoder, pon_pin: int, pon_pol: int, band_sel_pin:int, preferred_band:int, retry_minute=10, sync_indicator_pin=17):
        """
        コンストラクタ
        Args:
            jjydec: JJYDecoderのインスタンス
            pon_pin: 電源制御（PON）を接続しているGPIO番号
            pon_pol: 電源制御の極性（電源オンになる値）
            band_sel_pin: バンド選択を接続しているGPIO番号
            preferred_band: 優先したいバンド（1か0）
            retry_minute: JJYデコード試行のリトライ時間（分）
            sync_indicator_pin: 同期インジケーターLEDのGPIO
        """
        # JJYデコーダーにコールバックを設定
        self.jjy = jjydec
        self.jjy.add_callback(self.decoded)
        # 電源制御
        self.pon = Pin(pon_pin, Pin.OUT)
        # まず電源を切っておく
        self.pon.value(pon_pol ^ 1)
        self.pon_polality = pon_pol
        # バンド選択
        self.band_select = Pin(band_sel_pin, Pin.OUT)
        self.estimated_band = preferred_band
        self.band_select.value(self.estimated_band)

        self.retry_count = retry_minute           # リトライ分

        self.first_try = True               # 初回試行
        self.try_counter = 0                # 試行カウンタ
        self.idle_counter = 0               # アイドリングカウンタ

        # 現在のステート
        self.state = STATE_TRY
        # 同期インジケーター
        self.sync_indicator = Pin(sync_indicator_pin,mode=Pin.OUT)
        self.sync_indicator.value(0)    # まず消灯
        # タイマー
        self.tm = Timer()
        # タイマーハンドラ起動時呼び出し
        self._timer_handler(self.tm)
    
    def sync_start(self):
        """強制同期スタート"""
        if self.state == STATE_IDLE:
            self.idle_counter = 0   # カウンタリセット
            self.state = STATE_TRY
    
    def sync_stop(self):
        """同期停止"""
        if self.state == STATE_TRY or self.state == STATE_RETRY:
            self.state = STATE_IDLE
            self.try_counter = 0                    # カウンタリセット
            self.idle_counter = 0
            self.jjy.stop()                         # 一旦停止
            self.pon.value(self.pon_polality ^ 1)   # 一旦電源を切る

    def _tick(self, arg):
        """
        タイマー割り込みからスケジュールされる状態遷移・制御ロジック
        """
        self.dprint("--- tick %d---" % (self.idle_counter))
        if self.state == STATE_TRY or self.state == STATE_RETRY:
            if self.try_counter == 0:     # 試行開始
                self.dprint("--- Try start ---")
                # JJY起動
                self.band_select.value(self.estimated_band)     # バンド設定
                self.pon.value(self.pon_polality)               # 電源オン
                self.jjy.restart()
                # インジケーターLED消灯
                self.sync_indicator.value(0)

            self.try_counter += 1
            # 試行回数を超えている
            if self.try_counter > self.retry_count:
                self.try_counter = 0                    # カウンタリセット
                self.jjy.stop()                         # 一旦停止
                self.pon.value(self.pon_polality ^ 1)   # 一旦電源を切る
                if self.state == STATE_TRY:
                    self.state = STATE_RETRY
                    self.dprint("--- Retry start ---")
                    self.estimated_band ^= 1            # バンドを変えてみる
                    time.sleep(5)   # 少し待つ
                elif self.state == STATE_RETRY:
                    self.estimated_band ^= 1            # バンドを戻す
                    if self.first_try:                  # バンドを変えて試行を繰り返す
                        self.state = STATE_TRY
                        time.sleep(5)               # 少し待つ
                    else:
                        self.state = STATE_IDLE         # 諦める
                        self.sync_indicator.value(0) # インジケータ消灯

        elif self.state == STATE_IDLE:
            self.idle_counter += 1
            if self.idle_counter >= 60:                 # アイドル1時間経過
                self.idle_counter = 0
                self.try_counter = 0
                self.state = STATE_TRY                  # 時間合わせの試行を開始

    def _timer_handler(self, t):
        """
        1分周期のハードウェアタイマーハンドラ。
        MicroPythonのGCストールを避けるため、実際の処理はschedule()に委譲する。
        """
        schedule(self._tick, 0)
        self.tm.init(mode=Timer.ONE_SHOT, period=1000*60, callback=self._timer_handler)

    def decoded(self, args):
        """
        JJY信号のデコード成功時に呼ばれるコールバック
        """
        self.first_try = False
        self.state = STATE_IDLE         # 成功したのでアイドルに切り替える
        self.try_counter = 0            # カウンタリセット
        self.idle_counter = 0
        self.dprint("--- Succeeded JJY signal decode ---")
        # インジケーター点灯
        self.sync_indicator.value(1)
        # 電源を切る
        self.jjy.stop()
        self.pon.value(self.pon_polality ^ 1)
