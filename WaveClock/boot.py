"""
SMPSをPWMモードに切り替える
"""
from machine import Pin
from utime import sleep

smps_mode = Pin(23, Pin.OUT)
smps_mode.value(1)
