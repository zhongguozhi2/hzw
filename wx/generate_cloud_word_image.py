# make_heart_wordcloud.py
"""
在 Windows 上运行，输入文件: [OCR]_record_screen_20251010_1604.txt
输出文件: heart_wordcloud.png

依赖:
    pip install jieba wordcloud pillow matplotlib numpy

说明:
- 脚本会尝试找到常见的中文字体（微软雅黑 / 黑体 等），如果没有请手动改 FONT_PATH 指向你的 .ttf/.ttc。
- 生成的图片将是一个红色爱心背景，词为白色（你可改为其他配色）。
"""

from collections import Counter
import os
import re
import sys
import jieba
import numpy as np
from PIL import Image, ImageDraw
from wordcloud import WordCloud
import matplotlib.pyplot as plt

# ---------- 配置区（按需修改） ----------
INPUT_FILE = "[OCR]_record_screen_20251010_1604.txt"   # 你的聊天文件（放在脚本同目录）
OUTPUT_FILE = "heart_wordcloud.png"                   # 输出图片文件名
WIDTH = 1200                                         # 图片宽（像素）
HEIGHT = 1200                                        # 图片高（像素）
MAX_WORDS = 100                                      # 词云最大词数
SCALE = 2                                            # 高清放大倍数（保存更清晰）
# 备用的 Windows 中文字体路径（脚本会自动选第一个存在的）
CANDIDATE_FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",    # 微软雅黑（多字库）
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体
    r"C:\Windows\Fonts\simsun.ttc",  # 宋体
    r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc",
]
# 你的停用词（直接把你提供的停用词贴进来）
STOPWORDS = set([
    '的', '了', '在', '是', '我', '你', '有', '和', '就',
    '不', '人', '都', '一', '一个', '上', '也', '很', '到',
    '说', '要', '去', '你', '我', '吗', '呢', '吧', '啊',
    '这个', '那个', '然后', '就是', '可以', '因为', '所以',
    '但是', '如果', '还是', '知道', '觉得', '什么', '怎么',
    '为什么', '怎么', '这样', '那样', '这么', '那么', '现在',
    '今天', '明天', '昨天', '时候', '我们', '他们', '你们',
    '这些', '那些', '这个', '那个', '一些', '一点', '一下',
    '一定', '一起', '一直', '一样', '一切', '一下', '一些',
    '一点', '一种', '一样', '一切', '一下', '一些', '一点',
    '一种', '一样', '一切', '一下', '一些', '一点', '一种',
    '哈哈', '呵呵', '嘿嘿', '嘻嘻', '哦', '嗯', '好的', '好吧',
    '好的', '好吧', '好的', '好吧', '好的', '好吧', '好的', '好吧',
    '京世', '京东', '家电', '野趣', '串烧', '不是', '没有', '感觉', '消息', '应该',
    '以为', '撤回', '已经', '一条', '自己', '刚刚', '看着', '还有', '之前',
    '可能', '结束', '对方', '看到', '不能', '这是', '不会', '有点',
    '发起', '是不是', '直接', '好像', '发现', '竟然', '这边', '小时', '里面',
    '小烧', '本来', '这种', '多少', '赶紧', '不想', '地方', '拒绝', '问题',
    '表情', '一句', '一次', '共享', '我要', '东西', '真是', '开始', '出来',
    '干嘛', '记得', '为啥', '确实', '无应答', '正常', '试试', '真的', '不要', '打算',
    '需要', '一天', '不过', '好多', '回来', '以后', '估计', '不吃',
    '结果', '还要', '还好', '旁边', '给我发', '不行', '不用', '过来', '微信', '回头',
    '两个', '终于', '那边', '时间', '不下', '想着', '视频', '只能', '貌似',
    '啥时候', '每天', '突然', '没想到', '中断', '一看', '认识', '猜猜', '嘟嘟',
    '一块', '昨天下午', '哪个', '比较', '只有', '不到', '当然', '肯定', '其他',
    '其实', '分钟', '腾讯', '而且', '不好', '怎么样', '猛一看', '回去', '几点', 
    '起来', '过去', '松江区', '空调', '地铁站', '上午', '下午', '中午', '晚上', '凌晨'
])

# ---------- 辅助函数 ----------
def choose_font(candidates):
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def read_text_file(path, encoding_candidates=('utf-8', 'gb18030', 'gbk', 'utf-16')):
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到输入文件: {path}")
    for enc in encoding_candidates:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    # 最后再用二进制强行读取并尝试忽略错误
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        return raw.decode('utf-8', errors='ignore')
    except:
        return raw.decode('utf-8', 'ignore')

# 用数学方程生成心形 mask（高质量）
def make_heart_mask(width, height):
    # 将坐标映射到 -1.5..1.5 的区间以包含心形
    x = np.linspace(-1.5, 1.5, width)
    y = np.linspace(1.5, -1.5, height)  # 反向，以便图像不倒
    X, Y = np.meshgrid(x, y)
    # 心形方程 (x^2 + y^2 - 1)^3 - x^2 y^3 <= 0
    Z = (X**2 + Y**2 - 1)**3 - (X**2) * (Y**3)
    mask = np.uint8(Z <= 0) * 255
    return mask

def clean_and_cut(text, stopwords):
    # 只保留中英文与数字（去掉表情、标点、特殊符）
    text = re.sub(r'[^\u4e00-\u9fff]+', ' ', text)
    # 分词（jieba）
    words = jieba.cut(text, cut_all=False)
    # 过滤停用词、单字符英文/数字按需保留（这里去掉长度为1的英文/数字）
    filtered = []
    for w in words:
        w = w.strip()
        if not w:
            continue
        if w in stopwords:
            continue
        # 如果全是英文或数字，且长度为1，跳过
        if re.fullmatch(r'[A-Za-z0-9]', w):
            continue
        if len(w) == 1:
            continue
        filtered.append(w)
    return filtered

# ---------- 主流程 ----------
def main():
    print("开始生成爱心词云...")

    # 1) 字体选择
    font_path = choose_font(CANDIDATE_FONTS)
    if font_path:
        print(f"使用字体: {font_path}")
    else:
        print("警告: 未找到预设字体，请手动修改 FONT_PATH 为你系统中的中文字体路径（.ttf 或 .ttc）。")
        font_path = None  # WordCloud 需要字体路径，否则中文会显示方块

    # 2) 读取源文本
    text = read_text_file(INPUT_FILE)
    print(f"已读取文本（长度 {len(text)} 字符）")

    # 3) 清洗并分词
    filtered_words = clean_and_cut(text, STOPWORDS)
    # 统计词频
    word_freq = Counter(filtered_words)
    
    # 选择最常用的100个词
    top_words = dict(word_freq.most_common(75))
    print(top_words)
    # assert 0
    # 4) 生成心形 mask
    mask_arr = 255 - make_heart_mask(WIDTH * SCALE, HEIGHT * SCALE)  # 高分辨率 mask
    # WordCloud 期望 mask 中 255 表示可用区域，0 表示屏蔽区域 —— 我们生成的是符合的
    print("已生成心形 mask")

    # 5) 生成词云（透明背景，RGBA 模式）
    if not font_path:
        raise RuntimeError("找不到字体路径，无法正确渲染中文，请在脚本中将 FONT_PATH 设置为你机器上的中文字体路径。")

    wc = WordCloud(
        font_path=font_path,
        background_color=None,   # 透明背景
        mode="RGBA",
        max_words=MAX_WORDS,
        width=WIDTH * SCALE,
        height=HEIGHT * SCALE,
        mask=mask_arr,
        prefer_horizontal=0.9,
        relative_scaling=0.5,
        collocations=False,      # 避免词组自动合并
    )

    wc.generate_from_frequencies(top_words)
    # 把词全部设为白色（你可以改成其它颜色函数）
    wc.recolor(color_func=lambda *args, **kwargs: "white")

    # 6) 准备红色爱心背景图并合成
    # 创建纯红背景
    red_bg = Image.new("RGBA", (WIDTH * SCALE, HEIGHT * SCALE), (220, 30, 50, 255))  # 红色背景，可调整
    cloud_img = wc.to_image()  # RGBA 图像，文字部分有不透明像素，背景透明

    # 我们希望图片外的区域（mask==0）保持为背景色（红），
    # cloud_img 是整个矩形，有文字像素和透明区域，直接在 red_bg 上粘贴即可（alpha 作为掩码）
    red_bg.paste(cloud_img, (0, 0), cloud_img)

    # 7) 裁剪到包含心形的边界（可选），这里保留整个画布尺寸
    final = red_bg.resize((WIDTH, HEIGHT), Image.LANCZOS)  # 缩回目标尺寸以防太大

    # 8) 保存
    final.save(OUTPUT_FILE)
    print(f"词云已保存为: {OUTPUT_FILE}")

    # 9) 显示（可选，在 Windows 会弹窗）
    try:
        plt.figure(figsize=(8,8))
        plt.imshow(np.array(final))
        plt.axis("off")
        plt.show()
    except Exception as e:
        print("显示图片失败：", e)

if __name__ == "__main__":
    main()
