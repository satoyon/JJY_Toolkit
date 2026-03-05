from machine import RTC
from machine import Pin
import rp2
import utime as time
import ntptime

import network
from config import WIFI_CONFIG


# 40kHzキャリア発振ステートマシン
@rp2.asm_pio(
    set_init=(rp2.PIO.OUT_LOW),
    autopull=False,
)
def _40kHz_osc():
    wrap_target()
    wait(0, irq, 4)     # IRQ4 = on/off: キャリア発振/停止
    set(pins, 1)        # High
    nop()               # 1Clock
    set(pins, 0)        # Low
    wrap()

# JJY変調ステートマシン
@rp2.asm_pio(
    autopull=False,
    sideset_init=(rp2.PIO.OUT_LOW),
    fifo_join=rp2.PIO.JOIN_TX
)
def _JJY_Pulse():
    irq(4).side(0)              # IRQ4 Set / Carrier stop
    wrap_target()
    pull(block)         # 1
    mov(x, osr)         # 2
    pull(block)         # 3
    mov(y, osr)         # 4
    irq(clear,4).side(1)        # IRQ4 clear/ Carrier start
    label("send_loop")
    jmp(x_dec, "send_loop")
    irq(4).side(0)              # IRQ4 Set / Carrier stop
    label("wait_loop")
    jmp(y_dec, "wait_loop")
    wrap()

# JJY変調コード
JJY_PULSE_CODE = ((800*1000-5,200*1000-1),    # 0 = 800ms carrier + 200ms blank
                  (500*1000-5,500*1000-1),    # 1 = 500ms carrier + 500ms blank
                  (200*1000-5,800*1000-1))    # Position Marker = 200ms carrier + 800ms blank

JJY_MARKER = 2

# JJYタイムコードエンコーダー
def jjy_encode(minute, hour, yearday, year, weekday):
    code = [0] * 60
    pa1 = 0     # parity
    pa2 = 0

    # marker
    for i in (0, 9, 19, 29, 39, 49, 59):
        code[i] = JJY_MARKER

    # minute
    m10, m1 = minute // 10, minute % 10
    code[1], code[2], code[3] = (m10 >> 2) & 1, (m10 >> 1) & 1, m10 & 1
    code[5], code[6], code[7], code[8] = (m1 >> 3) & 1, (m1 >> 2) & 1, (m1 >> 1) & 1, m1 & 1
    pa2 = (code[1]+code[2]+code[3]+code[5]+code[6]+code[7]+code[8]) % 2

    # hour
    h10, h1 = hour // 10, hour % 10
    code[12], code[13] = (h10 >> 1) & 1, h10 & 1
    code[15], code[16], code[17], code[18] = (h1 >> 3) & 1, (h1 >> 2) & 1, (h1 >> 1) & 1, h1 & 1
    pa1 = (code[12]+code[13]+code[15]+code[16]+code[17]+code[18]) % 2

    # yearday
    yd100, yd10, yd1 = yearday // 100, (yearday % 100) // 10, yearday % 10
    code[22], code[23] = (yd100 >> 1) & 1, yd100 & 1
    code[25], code[26], code[27], code[28] = (yd10 >> 3) & 1, (yd10 >> 2) & 1, (yd10 >> 1) & 1, yd10 & 1
    code[30], code[31], code[32], code[33] = (yd1 >> 3) & 1, (yd1 >> 2) & 1, (yd1 >> 1) & 1, yd1 & 1

    # parity
    code[36] = pa1
    code[37] = pa2

    # year下2桁
    year %= 100
    y10, y1 = year // 10, year % 10
    code[41], code[42], code[43], code[44] = (y10 >> 3) & 1, (y10 >> 2) & 1, (y10 >> 1) & 1, y10 & 1
    code[45], code[46], code[47], code[48] = (y1 >> 3) & 1, (y1 >> 2) & 1, (y1 >> 1) & 1, y1 & 1

    # weekday
    jjy_weekday = (weekday + 1) % 7 
    code[50], code[51], code[52] = (jjy_weekday >> 2) & 1, (jjy_weekday >> 1) & 1, jjy_weekday & 1

    return code

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

# RTCをNTPで設定
def setup_rtc_from_ntp():
    conn = wifi_connect(WIFI_CONFIG["ssid"], WIFI_CONFIG["pass"])
    if conn is not None:
        conn.ifconfig()
        time.sleep(1)
        rtc = RTC()
        ntptime.host = 'ntp.nict.jp'    # 日本用
        now = time.localtime(ntptime.time() + 9 * 60 * 60)
        rtc.datetime((now[0], now[1], now[2], now[6], now[3], now[4], now[5], 0))
        print("Set RTC to %d/%d/%d, %d:%d:%d" % (now[0], now[1], now[2], now[3], now[4], now[5]))
        conn.active(False)
        conn = None
    else:
        print("Cant connect to %s" % WIFI_CONFIG["ssid"])


# RTCをあわせる間隔（分）
EXPIRE = 60 * 6  # 6時間に1回RTCを補正する
# 疑似JJY出力ポート
OSC_OUT = 16
INDICATOR_PIN = 15

if __name__ == "__main__":
    # 疑似JJY送信機の準備
    osc = Pin(OSC_OUT, Pin.OUT)
    osc.value(0)
    # 160kHz / 4 = 40kHz
    sm_osc  = rp2.StateMachine(0, _40kHz_osc, freq=160000, set_base=osc)
    # 1MHz = 1us
    sm_jjy = rp2.StateMachine(1, _JJY_Pulse, freq=1000000,sideset_base=Pin(INDICATOR_PIN))
    # 先にsm_jjyを起動してIRQ4を立てておく
    sm_jjy.active(1)
    sm_osc.active(1)
    
    # 時間計測カウンタ（分）
    counter = EXPIRE + 1
    try:
        while(True):
            counter += 1
            # 初回及びEXPIRE分おきにRTCを更新して時間を調整
            if counter > EXPIRE:
                counter = 0
                # FIFOが空になるまで待つ
                while sm_jjy.tx_fifo() != 0:
                    time.sleep(1)
                # 更に待つ
                time.sleep(2)
                # これで疑似JJYの送信は停止しているはず
                # sm.active(0)からのリスタートが何故か機能しないのでこの方法で止めるしかない
                # NTPでRTCを更新
                try:
                    setup_rtc_from_ntp()
                except Exception:
                    # なにか問題が起きても無視する
                    pass
            # 次の0秒を待つ
            while True:
                now = time.localtime()
                if now[5] == 0:
                    break
            
            jjy_code = jjy_encode(now[4], now[3], now[7], now[0], now[6])
            if sm_jjy.tx_fifo() != 0:
                # 送信し終わってない場合、RTCに調整が入ってズレた可能性があるので1分飛ばす
                time.sleep(1)
                continue
            # JJYタイムコード送信
            for code in jjy_code:
                # ブロックしても構わない
                sm_jjy.put(JJY_PULSE_CODE[code][0])
                sm_jjy.put(JJY_PULSE_CODE[code][1])

    except KeyboardInterrupt:
        print("keyboard interrupt")
    finally:
        sm_osc.active(0)
        sm_jjy.active(0)
        # PIO0からすべてのPIOコードを削除して終了する
        pio0 = rp2.PIO(0)
        pio0.remove_program()
        Pin(OSC_OUT, Pin.OUT).low()
