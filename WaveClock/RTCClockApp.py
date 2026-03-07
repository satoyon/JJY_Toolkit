from Debug import Debug
from machine import Pin
from machine import RTC
import utime as time
from tm1637 import TM1637
from TimeSource import TimeSource
from TimeSyncer import TimeSyncer
from micropython import schedule
from machine import Timer
from machine import idle

MODE_TIME = 0
MODE_DATE = 1
MODE_WDAY = 2
MODE_SEC  = 3

WEEKDAYS=("non","tuE","uEd","tHu","Fri","SAt","Sun")

class RTCClockApp(Debug):
    """RTCを用いた時計アプリケーションクラス"""

    def __init__(self, display_dev: TM1637, time_source: TimeSource, time_sync: TimeSyncer, mode_select_pin: int, force_sync_pin: int):
        """
        コンストラクタ
        Args:
            display_dev: TM1637のインスタンス
            time_source: TimeSourceのインスタンス
            time_sync: TimeSyncerのインスタンス
            mode_select_pin: 表示モード切替スイッチが接続されているGPIO番号
            force_sync_pin: 強制受信スイッチが接続されているGPIO番号
        """
        self.disp = display_dev
        self.timesrc = time_source
        self.timesync = time_sync
        # タイマー10ms
        self.tm = Timer()
        # 表示更新処理中フラグ（キュー溢れ防止用）
        self._updating = False
        # 1つ前の秒
        self.prev_sec = -1
        # 初期表示
        self.disp.show_str("----")
        # RTCに現在日時が設定されているか？
        self.setup_rtc = False
        # TimeSourceにコールバック関数を登録
        self.timesrc.add_callback(self.adjust_rtc)
        # 表示モード
        self.mode = MODE_TIME
        # 1つ前の表示モード
        self.prev_mode = self.mode
        # キースイッチ設定
        self._last_keydown_times = {} # キー押下時間を格納する辞書
        self.mode_select = Pin(mode_select_pin, Pin.IN, pull=Pin.PULL_UP)
        self.force_sync = Pin(force_sync_pin, mode=Pin.IN, pull=Pin.PULL_UP)
        self.mode_select.irq(self._key_event_handler,trigger=Pin.IRQ_FALLING)
        self.force_sync.irq(self._key_event_handler,trigger=Pin.IRQ_FALLING)
    
    def _key_event_handler(self, p):
        """スイッチ押下時の割り込みハンドラ"""
        key_id = id(p)
        now = time.ticks_ms()
        last_time = self._last_keydown_times.get(key_id, 0)
        if time.ticks_diff(now, last_time) > 500:    # チャタリング防止: 500ms以上経過していたら
            self._last_keydown_times[key_id] = now
            schedule(self._key_down, p)
    
    def _key_down(self, p):
        """キーダウンイベント処理（非同期コンテキストで実行）"""
        if p == self.mode_select:       # 表示モード選択
            self.mode = (self.mode + 1) % 4
        elif p == self.force_sync:      # 強制受信
            self.timesync.sync_start()

    def adjust_rtc(self, args):
        """
        RTCに現在日時を設定するコールバック関数
        Args:
            args: (jjy_time, ticks_ms)
            jjy_time: RTCに書き込むUNIXエポックタイム
            ticks_ms: この時間を受信したtime.ticks_ms()
        """
        jjy_time, ticks_ms = (args)

        rtc = RTC()
        elapsed_ms = time.ticks_diff(time.ticks_ms(), ticks_ms)
        rtc_time = jjy_time + (elapsed_ms // 1000) + 1
        now = time.localtime(rtc_time)
        # 次の秒が来るまでスリープしてタイミングを合わせる
        time.sleep_ms(1000 - (elapsed_ms % 1000))
        rtc.datetime((now[0], now[1], now[2], now[6], now[3], now[4], now[5], 0))
        self.dprint("Set RTC to %d/%d/%d, %d:%d:%d" % (now[0], now[1], now[2], now[3], now[4], now[5]))

        self.setup_rtc = True
    
    @micropython.native
    def _timer_handler(self,t):
        """
        10msタイマー割り込みハンドラ
        実際の処理はschedule()に委譲
        """
        # 前回の処理が終わっていない、またはキューが一杯の場合はスキップする
        if not self._updating:
            try:
                schedule(self._update_display, None)
                self._updating = True
            except RuntimeError:
                self.dprint("--- schedule() queue full ---")

    @micropython.native
    def _update_display(self, _):
        """
        表示の更新を行う（メインスレッドで実行）
        """
        try:
            now = time.localtime()
            sec = now[5]
            if self.prev_sec != sec or self.prev_mode != self.mode:
                self.prev_sec = sec
                self.prev_mode = self.mode
                # 表示更新
                disp_str = "----"
                if self.setup_rtc:
                    if self.mode == MODE_TIME:
                        if now[5] % 2 == 0:
                            disp_str = "%2d:%02d" % (now[3],now[4])
                        else:
                            disp_str = "%2d%02d" % (now[3],now[4])
                    elif self.mode == MODE_DATE:
                        disp_str = "%2d%2d" % (now[1], now[2])
                    elif self.mode == MODE_WDAY:
                        disp_str = " %s" % (WEEKDAYS[now[6]])
                    elif self.mode == MODE_SEC:
                        disp_str = "%2d%2d" % (now[4], now[5])
                self.disp.show_str(disp_str)
        finally:
            # 処理完了（またはエラー発生）時にフラグを下ろす
            self._updating = False
    
    def run(self):
        """
        アプリケーションメインループ
        """
        self.tm.init(mode=Timer.PERIODIC, period=10, callback=self._timer_handler)
        try:
            while True:
                idle()
        except Exception as e:
            self.dprint(e)
        finally:
            self.tm.deinit()
