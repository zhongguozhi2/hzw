import pytesseract
from PIL import Image
import cv2
import numpy as np
import os

class ImageTextExtractor:
    def __init__(self, tesseract_path=None):
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    
    def preprocess_image(self, image_path):
        """图像预处理"""
        try:
            # 读取图片
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError("无法读取图片")
            
            # 转换为灰度图
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
            
            # 二值化
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            return thresh
        except Exception as e:
            print(f"图像预处理错误: {e}")
            return None
    
    def extract_text(self, image_path, lang='chi_sim'):
        """提取图片中的文字"""
        try:
            # 预处理图片
            processed_img = self.preprocess_image(image_path)
            
            if processed_img is None:
                # 如果预处理失败，直接使用原图
                processed_img = Image.open(image_path)
            else:
                processed_img = Image.fromarray(processed_img)
            
            # 提取文字
            text = pytesseract.image_to_string(processed_img, lang=lang)
            
            return text.strip()
        
        except Exception as e:
            return f"提取文字时出错: {e}"
    
    def extract_text_with_confidence(self, image_path, lang='chi_sim+eng'):
        """提取文字并返回置信度"""
        try:
            processed_img = self.preprocess_image(image_path)
            
            if processed_img is None:
                processed_img = Image.open(image_path)
            else:
                processed_img = Image.fromarray(processed_img)
            
            # 获取详细数据
            data = pytesseract.image_to_data(processed_img, lang=lang, output_type=pytesseract.Output.DICT)
            
            results = []
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 30:  # 只保留置信度大于30的结果
                    text = data['text'][i].strip()
                    if text:
                        results.append({
                            'text': text,
                            'confidence': int(data['conf'][i]),
                            'position': {
                                'left': data['left'][i],
                                'top': data['top'][i],
                                'width': data['width'][i],
                                'height': data['height'][i]
                            }
                        })
            
            return results
        
        except Exception as e:
            return f"提取文字时出错: {e}"

# 使用示例
if __name__ == "__main__":
    pytesseract.pytesseract.tesseract_cmd = r'D:\program\tesseract\tesseract.exe'
    image_dir = 'record_screen'
    extractor = ImageTextExtractor()
    with open('result.txt', 'a', encoding='utf-8') as f:
        for image_file_name in os.listdir(image_dir)[:10]:
            print('正在处理图片: {}'.format(image_file_name))
            # 提取文字
            image_file_path = os.path.join(image_dir, image_file_name)
            text = extractor.extract_text(image_file_path)
            print("提取的文字:")
            print(text)
            f.write(text)
            # 提取带置信度的文字
            detailed_results = extractor.extract_text_with_confidence(image_file_path)
            print("\n详细结果:")
            for result in detailed_results:
                print('result', result)
                print(f"文本: {result['text']}, 置信度: {result['confidence']}%")