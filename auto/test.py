import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract
import os
import re
from collections import defaultdict
import json
pytesseract.pytesseract.tesseract_cmd = r'D:\program\tesseract\tesseract.exe'

class ChatScreenshotOCR:
    def __init__(self, tesseract_path=None):
        """初始化OCR系统"""
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # 聊天记录常见词汇词典（可扩展）
        self.chat_keywords = [
            # 时间相关
            '今天', '昨天', '刚才', '现在', '时间', '分钟', '小时',
            # 聊天常用语
            '你好', '在吗', '谢谢', '不好意思', '请问', '好的', '收到',
            '明白', '知道', '了解', 'OK', '嗯', '啊', '哦',
            # 标点符号
            '：', ':', '】', '【', '》', '《'
        ]
    
    def specialized_chat_preprocess(self, image_path):
        """专门针对聊天记录的预处理"""
        # 读取图像
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"无法读取图像: {image_path}")
        
        original_height, original_width = img.shape[:2]
        
        # 1. 分辨率提升（聊天记录通常需要更高分辨率）
        scale_factor = 1.5
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        
        # 2. 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 3. 针对聊天背景的特殊处理（通常有底色差异）
        # 使用CLAHE增强对比度
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)
        
        # 4. 多种二值化方法测试
        results = {}
        
        # 方法1: 自适应二值化（适合背景变化的聊天界面）
        adaptive_thresh = cv2.adaptiveThreshold(
            contrast_enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 15, 10
        )
        results['adaptive'] = adaptive_thresh
        
        # 方法2: Otsu二值化
        _, otsu_thresh = cv2.threshold(contrast_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        results['otsu'] = otsu_thresh
        
        # 方法3: 针对亮色背景聊天（如微信）
        _, inverted_otsu = cv2.threshold(contrast_enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        results['inverted'] = inverted_otsu
        
        return results, new_width, new_height
    
    def extract_chat_text_advanced(self, image_path, enable_multi_method=True):
        """高级聊天记录文字提取"""
        print(f"正在处理: {os.path.basename(image_path)}")
        
        best_result = ""
        best_confidence = 0
        best_method = ""
        
        # 获取预处理后的各种图像
        processed_images, width, height = self.specialized_chat_preprocess(image_path)
        
        for method_name, processed_img in processed_images.items():
            try:
                # 转换为PIL图像
                pil_img = Image.fromarray(processed_img)
                
                # 针对聊天记录优化的OCR配置
                configs = [
                    # 配置1: 适合密集文字
                    '--psm 6 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ一二三四五六七八九十百千万亿年月日时分秒abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,!?;:()[]{}【】《》「」''""',
                    # 配置2: 适合单行文字（聊天气泡）
                    '--psm 7 -c preserve_interword_spaces=1',
                    # 配置3: 自动页面分割
                    '--psm 3 -c preserve_interword_spaces=1'
                ]
                
                for config in configs:
                    try:
                        # 获取详细识别数据
                        data = pytesseract.image_to_data(
                            pil_img, 
                            lang='chi_sim+eng',
                            config=config,
                            output_type=pytesseract.Output.DICT
                        )
                        
                        # 计算置信度
                        confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                        if not confidences:
                            continue
                            
                        avg_confidence = sum(confidences) / len(confidences)
                        
                        # 提取有效文本
                        text_blocks = []
                        current_block = []
                        
                        for i in range(len(data['text'])):
                            text = data['text'][i].strip()
                            confidence = int(data['conf'][i])
                            
                            if text and confidence > 30:  # 置信度阈值
                                # 检查文本位置，判断是否属于同一行
                                if (current_block and 
                                    abs(data['top'][i] - data['top'][i-1]) > data['height'][i] * 0.8):
                                    # 新行开始
                                    text_blocks.append(' '.join(current_block))
                                    current_block = [text]
                                else:
                                    current_block.append(text)
                        
                        if current_block:
                            text_blocks.append(' '.join(current_block))
                        
                        full_text = '\n'.join(text_blocks)
                        
                        # 更新最佳结果
                        if avg_confidence > best_confidence and len(full_text.strip()) > 5:
                            best_confidence = avg_confidence
                            best_result = full_text
                            best_method = f"{method_name}_{config.split()[1]}"
                            
                    except Exception as e:
                        continue
                        
            except Exception as e:
                print(f"方法 {method_name} 失败: {e}")
                continue
        
        return best_result, best_confidence, best_method
    
    def post_process_chat_text(self, text):
        """专门针对聊天记录的后处理"""
        if not text:
            return ""
        
        # 1. 修复常见的OCR错误
        corrections = {
            '○': '〇',
            '—': '一',
            '': '吗',
            '': '嗯',
            '①': '一',
            '②': '二',
            '③': '三',
        }
        
        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)
        
        # 2. 合并被错误分割的中文字符
        text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
        
        # 3. 保留英文单词间的空格，但去除多余空格
        text = re.sub(r'([a-zA-Z])([\u4e00-\u9fff])', r'\1 \2', text)
        text = re.sub(r'([\u4e00-\u9fff])([a-zA-Z])', r'\1 \2', text)
        
        # 4. 清理特殊字符但保留中文标点
        chinese_punctuation = '，。！？、；："“”‘’（）《》【】'
        text = re.sub(r'[^\w\s\u4e00-\u9fff' + re.escape(chinese_punctuation) + ']', '', text)
        
        # 5. 标准化空格
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

def batch_process_chat_screenshots(folder_path, output_file='chat_records.json'):
    """批量处理聊天记录截图"""
    import glob
    
    ocr_engine = ChatScreenshotOCR()
    all_results = []
    
    # 支持的图片格式
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff']
    
    for extension in image_extensions:
        for image_path in glob.glob(os.path.join(folder_path, extension)):
            try:
                print(f"\n处理文件: {os.path.basename(image_path)}")
                
                # 提取文字
                text, confidence, method = ocr_engine.extract_chat_text_advanced(image_path)
                
                # 后处理
                processed_text = ocr_engine.post_process_chat_text(text)
                
                result = {
                    'filename': os.path.basename(image_path),
                    'text': processed_text,
                    'confidence': round(confidence, 2),
                    'method': method,
                    'char_count': len(processed_text)
                }
                
                all_results.append(result)
                
                print(f"置信度: {confidence:.2f}%")
                print(f"字符数: {len(processed_text)}")
                print(f"提取结果: {processed_text[:100]}...")
                
            except Exception as e:
                print(f"处理 {image_path} 时出错: {e}")
                continue
    
    # 保存结果到JSON文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    # 生成统计信息
    total_chars = sum(result['char_count'] for result in all_results)
    avg_confidence = sum(result['confidence'] for result in all_results) / len(all_results) if all_results else 0
    
    print(f"\n=== 处理完成 ===")
    print(f"处理文件数: {len(all_results)}")
    print(f"总字符数: {total_chars}")
    print(f"平均置信度: {avg_confidence:.2f}%")
    
    return all_results

# 使用示例
if __name__ == "__main__":
    # 单个文件测试
    ocr = ChatScreenshotOCR()
    
    # 处理单个聊天截图
    text, confidence, method = ocr.extract_chat_text_advanced(r'D:\cbc\hzw\auto\record_screen\1760077584.png')
    processed_text = ocr.post_process_chat_text(text)
    
    print(f"识别置信度: {confidence:.2f}%")
    print(f"使用方法: {method}")
    print("提取的聊天记录:")
    print(processed_text)
    
    # 批量处理文件夹中的所有截图
    # results = batch_process_chat_screenshots('./chat_screenshots/')