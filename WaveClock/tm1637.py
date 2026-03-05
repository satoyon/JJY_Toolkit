import rp2
from machine import Pin
import time

class TM1637:
    # 割り当て可能なステートマシンID管理
    _available_ids = list(range(8))
    
    # セグメントデータ定義 (Cコードの digit_seg / letter_seg に対応)
    _DIGIT_SEG = [0x3f, 0x06, 0x5b, 0x4f, 0x66, 0x6d, 0x7d, 0x07, 0x7f, 0x6f]
    _LETTER_SEG = {
        'A': 0x77, 'b': 0x7c, 'C': 0x39, 'd': 0x5e, 'E': 0x79, 'F': 0x71,
        'G': 0x3d, 'H': 0x76, 'i': 0x04, 'J': 0x0e, 'L': 0x38, 'n': 0x54,
        'o': 0x5c, 'P': 0x73, 'q': 0x67, 'r': 0x50, 'S': 0x6d, 't': 0x78,
        'u': 0x1c, 'y': 0x6e, '-': 0x40, ' ': 0x00
    }

    # PIOプログラム定義
    @rp2.asm_pio(
        out_init=(rp2.PIO.IN_HIGH),
        set_init=(rp2.PIO.IN_HIGH),
        sideset_init=(rp2.PIO.OUT_HIGH),
        out_shiftdir=rp2.PIO.SHIFT_RIGHT,
        autopull=False,
        fifo_join=rp2.PIO.JOIN_TX
    )
    def _tm1637_pio():
        wrap_target()
        # --- Start Condition ---
        pull(block)
        set(pindirs, 0b00)          # SDA/SCL input
        nop()                   [7]
        set(pindirs, 0b01)          # SDA output/SCL input
        set(pins, 0)                # SDA is Low
        nop()                   [7]
        set(pindirs, 0b11)             # SDA/SCL output
        set(x, 7)               .side(0)    # CLK is Low
        jmp("output")
        
        label("byte_loop")
        set(x, 7)       .side(0)    # CLK is Low
        pull(block)
        
        label("output")
        nop()                   [3]
        out(pins, 1)            [4] # LSB output
        nop()                   .side(1) # CLK is High
        nop()                   [7]
        nop()                   .side(0)    # CLK is Low
        jmp(x_dec, "output")
        
        # --- ACK Check ---
        set(pindirs, 0b10)      [7] # SDA input/SCL output
        nop()                   .side(1) # SCL = High
        jmp(pin, "nack")            # SDA High (NACK) なら分岐
        jmp("ack")
        
        label("nack")
        irq(rel(0))                 # NACK通知
        
        label("ack")
        nop()                   [6]
        nop()                   .side(0) # CLK is Low (ACK cycle end)
        set(pindirs, 0b11)      [7] # SDA/SCL Output
        out(x, 1)                   # 9bit目を読み取って判定
        jmp(not_x, "byte_loop")     # 0なら次のバイトへ
        
        # --- Stop Condition ---
        set(pins, 0)            [7] # SDA is Low
        nop()                   .side(1) # SCL is High
        nop()                   [7]
        set(pindirs, 0b00)      [7] # SDA/SCL Input (STOP)
        wrap()

    def __new__(cls, *args, **kwargs):
        if not cls._available_ids:
            raise RuntimeError("Maximum TM1637 instances (8) reached")
        instance = super().__new__(cls)
        instance.sm_id = cls._available_ids.pop(0)
        return instance

    def __init__(self, sda_pin, columns=6, contrast=3):
        # SDAの次のピンをSCLとする仕様を再現 (sda_base_pin + 1)
        self.sda_pin = Pin(sda_pin, Pin.IN, pull=Pin.PULL_UP)
        self.scl_pin = Pin(sda_pin + 1, Pin.IN, pull=Pin.PULL_UP)
        self.columns = columns
        
        # PIO初期化 (2MHz)
        self.sm = rp2.StateMachine(
            self.sm_id,
            self._tm1637_pio,
            freq=2000000,
            sideset_base=self.scl_pin,
            set_base=self.sda_pin, # SDA(bit0) & SCL(bit1) をまとめて制御
            out_base=self.sda_pin,
            jmp_pin=self.sda_pin
        )
        self.sm.active(1)
        
        # 初期表示設定
        self.clear()
        self.set_contrast(contrast)
    
    @micropython.native
    def _send_cmd(self, data, keep_going=False):
        # 9ビット目に「終了(1)」か「継続(0)」のフラグを立てる
        val = (data & 0xFF) | (0 if keep_going else 0x100)
        self.sm.put(val)

    def set_contrast(self, level):
        # 0x88 (Display ON) | 0~7
        cmd = 0x88 | (level & 0x07)
        self._send_cmd(cmd)

    def _chr_to_seg(self, char):
        if '0' <= char <= '9':
            return self._DIGIT_SEG[int(char)]
        return self._LETTER_SEG.get(char, 0x00)

    @micropython.native
    def show_str(self, s):
        # 文字列を解析してセグメントデータのリストを作成
        segments = []
        i = 0
        s_len = len(s)
        
        # カラム数または文字列が終わるまでループ
        while i < s_len and len(segments) < self.columns:
            char = s[i]
            base_seg = self._chr_to_seg(char)
            
            # 次の文字が存在し、かつドットかコロンの場合
            if (i + 1) < s_len and s[i + 1] in ('.', ':'):
                base_seg |= 0x80  # 8ビット目(ドット)を立てる
                i += 1            # ドット文字分インデックスを進める（スキップ）
            
            segments.append(base_seg)
            i += 1

        # 2. 生成したデータを出力
        # データセット（自動アドレスインクリメント）
        self._send_cmd(0x40) # TM1637_AUTOINC
        # アドレス設定 (0)
        self._send_cmd(0xC0, keep_going=True) # TM1637_ADDRSET
        
        # リストの内容を送信
        for j, seg in enumerate(segments):
            # 最後かどうかを判定 (リストの最後 かつ カラム最大)
            is_last = (j == len(segments) - 1)
            self._send_cmd(seg, keep_going=not is_last)

    def clear(self):
        self.show_str(' ' * self.columns)

    def release(self):
        self.sm.active(0)
        if self.sm_id not in self.__class__._available_ids:
            self.__class__._available_ids.append(self.sm_id)
            self.__class__._available_ids.sort()
