import matplotlib.pyplot as plt
from wordcloud import WordCloud
import jieba
import os

def generate_chinese_wordcloud(file_path, output_file='chinese_wordcloud.png'):
    """
    生成中文词云图
    
    参数:
    text: 中文文本
    output_file: 输出文件名
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        text = file.read()
    # 中文分词
    text_cut = " ".join(jieba.cut(text))
    
    # 获取系统中文字体路径（根据需要修改）
    # Windows系统常见中文字体路径
    font_path = 'C:/Windows/Fonts/simhei.ttf'  # 黑体
    
    # 如果是Linux系统，可以尝试
    # font_path = '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'
    
    # 或者是Mac系统
    # font_path = '/System/Library/Fonts/PingFang.ttc'
    
    # 创建词云对象，明确指定中文字体
    wordcloud = WordCloud(
        font_path=font_path,  # 这是关键！指定中文字体路径
        width=800, 
        height=600,
        background_color='white',
        max_words=200,
        max_font_size=100,
        collocations=False,
        stopwords={'一些', '要过滤'},  # 添加停用词
        contour_width=3,
        contour_color='steelblue'
    ).generate(text_cut)
    
    # 显示词云
    plt.figure(figsize=(10, 8))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.title('中文词云图', fontsize=16)
    plt.tight_layout(pad=0)
    
    # 保存图像
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.show()


# 生成中文词云
generate_chinese_wordcloud('text.txt', 'chinese_wordcloud.png')