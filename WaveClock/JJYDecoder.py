from machine import Pin
import rp2
from micropython import schedule
import utime as time
from Debug import Debug
from TimeSource import TimeSource

# インジケーターLEDのGPIO
INDICATOR_PIN = 25

@rp2.asm_pio(
    sideset_init=(rp2.PIO.OUT_LOW),
)
def jjy_capture_p():
    wrap_target()
    wait(1, pin, 0)          # 立ち上がりを待つ
    set(x, 0).side(1)        # カウンタのリセット
    
    label("loop")
    # --- 1ms 待機ブロック (10kHz動作時、10クロック消費) ---
    nop() [7]                # 8クロック
    nop()                    # 1クロック
    jmp(x_dec, "next")       # 1クロック (xをカウントダウン)
    
    label("next")
    jmp(pin, "loop")         # まだHighならループ継続（+1クロック）
    
    mov(isr, x).side(0)      # カウント結果をISRへ
    push()                   # Pythonへ送信
    irq(rel(0))
    wrap()

@rp2.asm_pio(
    sideset_init=(rp2.PIO.OUT_LOW),
)
def jjy_capture_n():
    wrap_target()
    wait(0, pin, 0)          # 立ち下がりを待つ
    set(x, 0).side(1)        # カウンタのリセット
    
    label("loop")
    # --- 1ms 待機ブロック (10kHz動作時、10クロック消費) ---
    nop() [7]                # 8クロック
    jmp(x_dec, "next")       # 1クロック (xをカウントダウン)
    
    label("next")
    jmp(pin, "success")      # Highならループ脱出（+1クロック）
    jmp("loop")              # Lowなのでループ継続（+1クロック）

    label("success")
    mov(isr, x).side(0)      # カウント結果をISRへ
    push()                   # Pythonへ送信
    irq(rel(0))
    wrap()

# 定数定義
JJY_ERROR  = 3      # エラー
JJY_P_MARK = 2      # ポジションマーカー
MARK_POSITIONS = (0, 9, 19, 29, 39, 49, 59)    # ポジションマーカーの位置

class JJYDecoder(Debug,TimeSource):
    """
    JJYデコーダークラス
    """

    def __init__(self, callback=None, smid = 0, input_port=15, input_pol=1, indicator_port=INDICATOR_PIN):
        """
        コンストラクタ

        Args:
            callback: コールバック関数 callback((jjy_time, received_ticks_ms)):
            jjy_time: 受信した日本標準時（UNIXエポックタイム）
            received_ticks_ms: jjy_timeを受信したtime.ticks_ms()
            smid: このクラスで使用するステートマシン番号
            input_port: JJY受信ユニットの出力が接続されているGPIO番号
            input_pol: JJY受信ユニットの出力極性、1=正論理、0=負論理
            idicator_port: インジケーターLEDのGPIO番号
        """
        # 60秒分のビットを格納するバッファ
        self.bit_buffer = [0] * 60
        # 現在の秒位置
        self.pos = 0
        # 同期が始まったならTrue
        self.synced = False
        # マーカーを識別したらTrue
        self.last_was_marker = False
        # 同期に成功した回数
        self.sync_counter = 0
        # 受信ステートマシンの割り込みが発生したticks_ms
        self.ticks_ms = 0
        # コールバック関数
        self.callback_funcs = []
        # ステートマシン番号
        self.sm_id = smid
        # JJY受信ステートマシンのロードと起動
        in_pin = Pin(input_port, Pin.IN, pull=-1)
        self.sm: rp2.StateMachine
        if input_pol == 1:  # 正論理
            self.sm = rp2.StateMachine(self.sm_id, jjy_capture_p, freq=10000, in_base=in_pin, jmp_pin=in_pin,sideset_base=Pin(indicator_port))
        else:   # 負論理
            self.sm = rp2.StateMachine(self.sm_id, jjy_capture_n, freq=10000, in_base=in_pin, jmp_pin=in_pin,sideset_base=Pin(indicator_port))
        self.sm.irq(self._pio_handler,1)
        self.add_callback(callback)
        # self.sm.active(1)

    @micropython.native
    def _pio_handler(self, p):
        """
        PIO割り込みハンドラ
        """
        schedule(self._jjy_interrupt, (p, time.ticks_ms()))

    @micropython.native
    def _jjy_interrupt(self, args):
        """
        JJY受信割り込みハンドラ
        """
        p, ticks = (args)
        pulse_width = 0x100000000 - int(self.sm.get())
        self.ticks_ms = ticks - pulse_width    # この信号の推定立ち上がり時間
 
        bit = JJY_ERROR                 # 3 はエラー
        if pulse_width < 100: pass      # おそらくはノイズ、無視する
        elif pulse_width < 350: bit = JJY_P_MARK    # ポジションマーカー
        elif pulse_width < 600: bit = 1
        elif pulse_width < 950: bit = 0
        else: pass                      # なんらかの異常

        self.dprint("pulse width=%d, bit=%d" % (pulse_width, bit))

        if bit == JJY_ERROR:            # エラーが起きたらいったんご破算にする
            self.synced = False
            self.pos = 0
        
        if bit == JJY_P_MARK:           # ポジションマーカー
            if self.last_was_marker:    # ポジションマーカーが2つ続いたら1フレーム開始
                self.dprint("--- Frame Sync ---")
                self.pos = 0
                self.synced = True      # 同期開始
            self.last_was_marker = True
            if self.synced:             # ポジションマーカーの位置をチェック
                if self.pos not in MARK_POSITIONS:
                    self.dprint("-- Error: Out of sync --")   # 同期が外れているのでご破算にする
                    self.synced = False
                    self.pos = 0
        else:
            self.last_was_marker = False
        
        if self.synced:
            self.bit_buffer[self.pos] = bit
            self.pos += 1
            # 1フレーム受信完了
            if self.pos >= 60:
                self.__decode_frame()
                self.pos = 0
                self.synced = False     # 継続せず
    
    @micropython.native
    def __decode_frame(self):
        """
        1フレーム60個分のデータを日本標準時にデコードするプライベート関数
        """
        # パリティチェック
        pa2 = (self.bit_buffer[1]+self.bit_buffer[2]+self.bit_buffer[3]+self.bit_buffer[5]+self.bit_buffer[6]+self.bit_buffer[7]+self.bit_buffer[8]) % 2
        pa1 = (self.bit_buffer[12]+self.bit_buffer[13]+self.bit_buffer[15]+self.bit_buffer[16]+self.bit_buffer[17]+self.bit_buffer[18]) % 2
        if pa1 != self.bit_buffer[36] or pa2 != self.bit_buffer[37]:    # エラー、デコードを諦める
            self.dprint("-- Parity Error --")
            return
        
        # minute
        m10 = self.bit_buffer[1] << 2 | self.bit_buffer[2] << 1 | self.bit_buffer[3]
        m1  = self.bit_buffer[5] << 3 | self.bit_buffer[6] << 2 | self.bit_buffer[7] << 1 | self.bit_buffer[8]
        minute = m10 * 10 + m1

        # hour
        h10 = self.bit_buffer[12] << 1 | self.bit_buffer[13]
        h1  = self.bit_buffer[15] << 3 | self.bit_buffer[16] << 2 | self.bit_buffer[17] << 1 | self.bit_buffer[18]
        hour = h10 * 10 + h1

        # yearday
        yd100 = self.bit_buffer[22] << 1 | self.bit_buffer[23]
        yd10  = self.bit_buffer[25] << 3 | self.bit_buffer[26] << 2 | self.bit_buffer[27] << 1 | self.bit_buffer[28]
        yd1   = self.bit_buffer[30] << 3 | self.bit_buffer[31] << 2 | self.bit_buffer[32] << 1 | self.bit_buffer[33]
        yearday = yd100 * 100 + yd10 * 10 + yd1

        # year
        y10 = self.bit_buffer[41] << 3 | self.bit_buffer[42] << 2 | self.bit_buffer[43] << 1 | self.bit_buffer[44]
        y1  = self.bit_buffer[45] << 3 | self.bit_buffer[46] << 2 | self.bit_buffer[47] << 1 | self.bit_buffer[48]
        year = y10 * 10 + y1 + 2000     # 2000年代は決め打ち

        # month, mday
        starting_sec = time.mktime((year,1,1,0,0,0,0,0))        # 起点＝本年1月1日0時0分
        target_sec   = starting_sec + (yearday - 1) * 86400     # 経過秒を加算
        current_dt   = time.localtime(target_sec)
        mday = current_dt[2]
        month = current_dt[1]

        # weekday
        jjy_weekday = self.bit_buffer[50] << 2 | self.bit_buffer[51] << 1 | self.bit_buffer[52]
        weekday = (jjy_weekday + 6) % 7

        # JJYから得た時刻を通知する
        jjy_time = time.mktime((year,month,mday,hour,minute,59,weekday,yearday))
        data = (jjy_time, self.ticks_ms)
        try:
            for callback in self.callback_funcs:
                if callback is not None:
                    schedule(callback, data)
        except RuntimeError:
            self.dprint("micropython.schedule queue full")

    def add_callback(self, callback):
        """
        時刻を通知するコールバック関数を登録する

        Args:
        callback: コールバック関数 callback((jjy_time, received_ticks_ms)):
            jjy_time: 受信した日本標準時（UNIXエポックタイム）
            received_ticks_ms: jjy_timeを受信したtime.ticks_ms()
        """
        if callback is not None:
            self.callback_funcs.append(callback)
    
    def stop(self):
        """ステートマシンの実行を一時停止する"""
        self.sm.active(0)
    
    def restart(self):
        """ステートマシンをリセットして再起動する"""
        self.sm.restart()
        self.sm.active(1)

    def release(self):
        """
        終了処理。
        ステートマシンを停止し、割り込みを解除した上でPIOコードをメモリから除去する。
        """
        # SM停止
        self.sm.active(0)
        # 割り込みハンドラ解除
        self.sm.irq(None, 1)
        # PIOコード除去
        pio_no = 0
        if self.sm_id > 3:
            pio_no = 1
        pio = rp2.PIO(pio_no)
        pio.remove_program()
