import jieba
import jieba.analyse
from wordcloud import WordCloud, ImageColorGenerator
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np
import re
from collections import Counter
import codecs

# 1. 准备数据
def load_chat_data(file_path):
    """读取微信聊天记录文件"""
    try:
        with codecs.open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except:
        with codecs.open(file_path, 'r', encoding='gbk') as f:
            content = f.read()
        return content

# 2. 文本预处理和分词
def process_text(text):
    """处理聊天文本，提取有效内容"""
    # 去除日期时间格式（根据你的聊天记录格式调整）
    text = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', text)
    text = re.sub(r'\d{2}:\d{2}', '', text)
    
    # 去除昵称和系统消息（根据实际情况调整）
    text = re.sub(r'你|我|\S+：', '', text)
    
    # 去除标点符号和数字
    text = re.sub(r'[^\u4e00-\u9fa5]', ' ', text)
    
    return text

# 3. 自定义停用词列表（重要！）
def get_stop_words():
    """获取停用词列表，去除无意义的词"""
    stop_words = set([
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
        '好的', '好吧', '好的', '好吧', '好的', '好吧', '好的', '好吧'
    ])
    return stop_words

# 4. 生成爱心形状的词云
def create_love_wordcloud(text, output_path='love_wordcloud.png'):
    """生成爱心形状的词云"""
    
    # 创建爱心形状的mask
    x, y = np.ogrid[:300, :300]
    mask = (x - 150) ** 2 + (y - 150) ** 2 > 130 ** 2
    mask = 255 * mask.astype(int)
    
    # 分词
    words = jieba.cut(text)
    stop_words = get_stop_words()
    
    # 过滤停用词和短词
    filtered_words = [
        word for word in words 
        if len(word) > 1 and word not in stop_words
    ]
    
    # 统计词频
    word_freq = Counter(filtered_words)
    
    # 选择最常用的100个词
    top_words = dict(word_freq.most_common(100))
    
    # 创建词云
    wc = WordCloud(
        font_path='simhei.ttf',  # 使用支持中文的字体，如微软雅黑、思源黑体等
        background_color='white',
        mask=mask,
        max_words=100,
        max_font_size=100,
        min_font_size=10,
        colormap='RdPu',  # 使用浪漫的粉紫色系
        width=800,
        height=800,
        random_state=42
    )
    
    # 生成词云
    wc.generate_from_frequencies(top_words)
    
    # 绘制并保存
    plt.figure(figsize=(10, 10))
    plt.imshow(wc, interpolation='bilinear')
    plt.axis('off')
    plt.tight_layout()
    
    # 保存图片
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.show()
    
    return output_path

# 主函数
def main():
    # 配置参数
    chat_file = '[OCR]_record_screen_20251010_1604.txt'  # 你的聊天记录文件路径
    output_file = '我们的爱情词云.png'  # 输出文件名
    
    # 加载聊天记录
    print("正在加载聊天记录...")
    chat_content = load_chat_data(chat_file)
    
    # 处理文本
    print("正在处理文本...")
    processed_text = process_text(chat_content)
    
    # 生成词云
    print("正在生成爱心词云...")
    result_path = create_love_wordcloud(processed_text, output_file)
    
    print(f"生成完成！文件保存为: {result_path}")
    print("这份充满爱意的礼物已经准备好了！💖")

# 运行程序
if __name__ == "__main__":
    main()