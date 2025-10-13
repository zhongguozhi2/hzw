"""获取聊天记录"""
import time
import uiautomator2 as u2
import os
d = u2.connect()
# while True:
#     # 滑动到聊天记录顶部
#     d.swipe(500, 550, 500, 1860, duration=0.1, steps=5)
#     time.sleep(0.1)
# 开始一屏幕一屏幕的往下滑，每一屏都截图，存放到record_screen目录下
# 2245, 240
os.makedirs('record_screen', exist_ok=True)  # 创建目录, 如果不存在
while True:
    d.swipe(500, 2240, 500, 240, duration=1)
    d.screenshot(f'record_screen/{int(time.time())}.png')
    time.sleep(1)