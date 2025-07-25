import os
import pygame
import sys
import random
import requests
from pygame.locals import *

# 初始化pygame
pygame.init()

# 设置窗口
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 500  # 增加了高度以容纳输入框
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption('研究生植物学障碍赛')

# 颜色
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (200, 200, 200)
LIGHT_GRAY = (240, 240, 240)
PINK = (255, 192, 203)

# 游戏参数
FPS = 30
clock = pygame.time.Clock()
font = pygame.font.SysFont('simhei', 20)
large_font = pygame.font.SysFont('simhei', 40)

# 劳务法学科名称
# subjects = [
#     "劳动合同法", "劳动争议调解仲裁法",
#     "社会保险法", "劳动安全卫生法",
#     "工资支付条例", "劳动监察条例",
#     "集体合同法", "职业培训法",
#     "女职工劳动保护", "未成年工特殊保护",
#     "工作时间与休息休假", "就业促进法"
# ]
subjects = [
    "植物学",          # 植物学（Botany）
    "植物生理学",       # 植物生理学（Plant Physiology）
    "植物生态学",       # 植物生态学（Plant Ecology）
    "植物分类学",       # 植物分类学（Plant Taxonomy）
    "植物解剖学",       # 植物解剖学（Plant Anatomy）
    "植物病理学",       # 植物病理学（Plant Pathology）
    "植物育种学",       # 植物育种学（Plant Breeding）
    "植物遗传学",       # 植物遗传学（Plant Genetics）
    "植物生物化学",     # 植物生物化学（Plant Biochemistry）
    "植物分子生物学",   # 植物分子生物学（Plant Molecular Biology）
    "植物细胞生物学",   # 植物细胞生物学（Plant Cell Biology）
    "植物营养学",       # 植物营养学（Plant Nutrition）
    "园艺学",           # 园艺学（Horticulture）
    "农学",             # 农学（Agronomy）
    "真菌学",           # 真菌学（Mycology）
    "藻类学",           # 藻类学（Phycology）
    "种子学",           # 种子学（Seed Science）
    "植物保护学",       # 植物保护学（Plant Protection）
    "植物资源学",       # 植物资源学（Plant Resources）
    "植物生物技术"      # 植物生物技术（Plant Biotechnology）
]

# 玩家设置
player_width = 50
player_height = 50
player_x = 100
player_y = WINDOW_HEIGHT - player_height - 50  # 调整了初始位置
player_rect = pygame.Rect(player_x, player_y, player_width, player_height)
player_vel_y = 0
is_jumping = False
player_speed = 5
jump_height = 20
gravity = 0.8

# 地面
ground_height = 50
ground_rect = pygame.Rect(0, WINDOW_HEIGHT - ground_height, WINDOW_WIDTH, ground_height)

# 障碍物设置
obstacles = []
obstacle_width = 40
obstacle_gap = 150
obstacle_speed = 4
char_height = 20  # 每个字符高度
char_spacing = 5  # 字符间距
top_margin = 10   # 顶部边距
# 最小高度=5个字+边距=5*20+4*5+2*10=120+20=140
# 最大高度=9个字+边距=9*20+8*5+2*10=220+20=240

# 红旗设置
flag_width = 50
flag_height = 80
flag_x = WINDOW_WIDTH - 100
flag_rect = pygame.Rect(flag_x, WINDOW_HEIGHT - flag_height - ground_height, flag_width, flag_height)

# 游戏状态
game_active = True
game_won = False
game_over = False
is_show_wishing_pool = False  # 是否显示许愿池

input_box = pygame.Rect(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 + 50, 300, 40)
input_text = ''
input_active = False
composing_text = ''  # 用于存储正在输入的拼音

# 许愿按钮
wish_button = pygame.Rect(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 110, 200, 50)
wish_sent = False  # 愿望是否已发送

# 企业微信机器人Webhook地址 (请替换为你的实际Webhook地址)
WECHAT_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=d49109f4-de4a-4234-9d9a-d08554b1f2df"

def reset_game():
    global player_rect, player_vel_y, is_jumping, obstacles, game_active, game_won, game_over, is_show_wishing_pool, input_text, wish_sent, composing_text
    player_rect.y = player_y
    player_vel_y = 0
    is_jumping = False
    obstacles = []
    game_active = True
    game_won = False
    game_over = False
    is_show_wishing_pool = False
    input_text = ''
    composing_text = ''
    wish_sent = False
    generate_obstacles()

def generate_obstacles():
    global obstacles
    obstacles = []
    x = 400
    
    while x < flag_x - 100:
        # 随机决定显示几个字(5-9个)
        word_count = random.randint(5, 9)
        # 计算所需高度
        height = word_count * char_height + (word_count - 1) * char_spacing + 2 * top_margin
        
        # 从学科名称中随机选取一个
        subject = random.choice(subjects)
        # 如果名称不够长，重复使用
        while len(subject) < word_count:
            subject += random.choice(subjects)
        # 截取所需长度
        subject = subject[:word_count]
        
        obstacles.append({
            'rect': pygame.Rect(x, WINDOW_HEIGHT - height - ground_height, 
                               obstacle_width, height),
            'subject': subject,
            'word_count': word_count
        })
        
        x += obstacle_gap + random.randint(-50, 50)

def draw_player():
    if player_img:
        window.blit(player_img, (player_rect.x, player_rect.y))
    else:
        # 如果没有图片，保留原来的方块绘制
        pygame.draw.rect(window, BLUE, player_rect)
        text = font.render("学生", True, WHITE)
        window.blit(text, (player_rect.x + 10, player_rect.y + 15))

def draw_obstacles():
    for obstacle in obstacles:
        pygame.draw.rect(window, RED, obstacle['rect'])
        
        subject = obstacle['subject']
        word_count = obstacle['word_count']
        total_text_height = word_count * char_height + (word_count - 1) * char_spacing
        start_y = obstacle['rect'].y + (obstacle['rect'].height - total_text_height) // 2
        
        for i, char in enumerate(subject):
            char_surface = font.render(char, True, WHITE)
            char_x = obstacle['rect'].x + (obstacle_width - char_surface.get_width()) // 2
            char_y = start_y + i * (char_height + char_spacing)
            window.blit(char_surface, (char_x, char_y))

def draw_flag():
    pygame.draw.rect(window, BLACK, (flag_rect.x, flag_rect.y, 5, flag_rect.height))
    if game_won:
        pygame.draw.polygon(window, GREEN, [
            (flag_rect.x + 5, flag_rect.y + 10),
            (flag_rect.x + flag_rect.width, flag_rect.y + flag_rect.height // 3),
            (flag_rect.x + 5, flag_rect.y + flag_rect.height // 1.5)
        ])
    else:
        pygame.draw.polygon(window, RED, [
            (flag_rect.x + 5, flag_rect.y + 10),
            (flag_rect.x + flag_rect.width, flag_rect.y + flag_rect.height // 3),
            (flag_rect.x + 5, flag_rect.y + flag_rect.height // 1.5)
        ])

def draw_ground():
    pygame.draw.rect(window, BLACK, ground_rect)

def draw_button():
    pygame.draw.rect(window, GREEN, wish_button)
    if wish_sent:
        text = font.render("已许愿", True, WHITE)
    else:
        text = font.render("许愿", True, WHITE)
    text_rect = text.get_rect(center=wish_button.center)
    window.blit(text, text_rect)

def show_game_over():
    text = large_font.render("游戏失败!", True, RED)
    text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 50))
    window.blit(text, text_rect)
    
    # 重新开始按钮
    restart_button = pygame.Rect(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50)
    pygame.draw.rect(window, GREEN, restart_button)
    restart_text = font.render("再来一次", True, WHITE)
    restart_text_rect = restart_text.get_rect(center=restart_button.center)
    window.blit(restart_text, restart_text_rect)
    return restart_button

def show_game_won():
    text = large_font.render("成功通过!", True, GREEN)
    text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 100))
    window.blit(text, text_rect)
    
    # 显示许愿池按钮
    wishing_pool_button = pygame.Rect(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 30, 300, 50)
    pygame.draw.rect(window, BLUE, wishing_pool_button)
    wishing_text = font.render("前往许愿池", True, WHITE)
    wishing_text_rect = wishing_text.get_rect(center=wishing_pool_button.center)
    window.blit(wishing_text, wishing_text_rect)
    return wishing_pool_button

def show_wishing_pool():
    # 许愿池背景
    pygame.draw.rect(window, LIGHT_GRAY, (WINDOW_WIDTH // 4, WINDOW_HEIGHT // 4, WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
    
    # 标题
    title = large_font.render("许愿池", True, BLUE)
    title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 4 + 40))
    window.blit(title, title_rect)
    
    # 提示文字
    hint = font.render("输入你的愿望:", True, BLACK)
    window.blit(hint, (WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 - 10))
    
    # 输入框
    color = BLUE if input_active else BLACK
    pygame.draw.rect(window, color, input_box, 2)
    pygame.draw.rect(window, WHITE, input_box)
    
    # 输入文本
    text_surface = font.render(input_text + composing_text, True, BLACK)
    window.blit(text_surface, (input_box.x + 5, input_box.y + 5))
    
    # 显示拼音输入状态
    if composing_text:
        composing_surface = font.render(composing_text, True, (100, 100, 100))
        window.blit(composing_surface, (input_box.x + 5 + text_surface.get_width(), input_box.y + 5))
    
    # 许愿按钮
    draw_button()
    
    # # 返回按钮
    # back_button = pygame.Rect(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 180, 200, 50)
    # pygame.draw.rect(window, GRAY, back_button)
    # back_text = font.render("返回游戏", True, BLACK)
    # back_text_rect = back_text.get_rect(center=back_button.center)
    # window.blit(back_text, back_text_rect)
    # return back_button

def send_to_wechat(message):
    """发送消息到企业微信机器人"""
    headers = {"Content-Type": "application/json"}
    data = {
        "msgtype": "text",
        "text": {
            "content": f"来自许愿池的新愿望:\n{message}"
        }
    }
    
    try:
        response = requests.post(WECHAT_WEBHOOK, json=data, headers=headers)
        return response.status_code == 200
    except Exception as e:
        print(f"发送失败: {e}")
        return False
def resource_path(relative_path):
    """获取资源的正确路径（兼容 PyInstaller 打包后的路径）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
# 在初始化部分添加
def load_images():
    try:
        # 加载背景图片（替换为你的图片路径）
        background_img = pygame.image.load(resource_path("background.jpg")).convert()
        background_img = pygame.transform.scale(background_img, (WINDOW_WIDTH, WINDOW_HEIGHT))
        
        # 加载玩家图片（替换为你的图片路径）
        player_img = pygame.image.load(resource_path("player.jpg")).convert_alpha()
        player_img = pygame.transform.scale(player_img, (player_width, player_height))
        
        return background_img, player_img
    except:
        print("图片加载失败，将使用默认图形")
        return None, None
background_img, player_img = load_images()

# 初始生成障碍物
generate_obstacles()

# 游戏主循环
running = True
while running:
    if background_img:
        window.blit(background_img, (0, 0))
    else:
        window.fill(PINK)  # 如果没有背景图片，使用白色背景
    
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False
        
        if event.type == KEYDOWN:
            if event.key == K_SPACE and not is_jumping and game_active:
                is_jumping = True
                player_vel_y = -jump_height
            
            if event.key == K_r and (game_over or (game_won and not is_show_wishing_pool)):
                reset_game()
            
            if input_active:
                if event.key == K_RETURN:
                    # 发送愿望
                    if input_text.strip() and not wish_sent:
                        if send_to_wechat(input_text):
                            wish_sent = True
                elif event.key == K_BACKSPACE:
                    if composing_text:
                        composing_text = composing_text[:-1]
                    elif input_text:
                        input_text = input_text[:-1]
                elif event.key == K_ESCAPE:
                    composing_text = ''
                else:
                    # 处理文本输入
                    if event.unicode.isprintable():
                        # 如果是普通字符
                        if len(event.unicode.encode('utf-8')) > 1:  # 可能是中文输入法的中间状态
                            composing_text += event.unicode
                        else:
                            # 如果是英文字符，直接添加到输入文本
                            if len(input_text + composing_text) < 20:
                                input_text += event.unicode
        
        # 处理文本编辑事件（用于中文输入法）
        if event.type == TEXTEDITING and input_active:
            composing_text = event.text
        
        # 处理文本输入事件（用于中文输入法确认）
        if event.type == TEXTINPUT and input_active:
            if len(input_text + event.text) < 20:
                input_text += event.text
            composing_text = ''
        
        if event.type == MOUSEBUTTONDOWN:
            if game_over:
                restart_button = show_game_over()
                if restart_button.collidepoint(event.pos):
                    reset_game()
            
            elif game_won and not is_show_wishing_pool:
                wishing_pool_button = show_game_won()
                if wishing_pool_button.collidepoint(event.pos):
                    is_show_wishing_pool = True
            
            elif is_show_wishing_pool:
                back_button = show_wishing_pool()
                
                # 检查是否点击了输入框
                if input_box.collidepoint(event.pos):
                    input_active = True
                else:
                    input_active = False
                
                # 检查是否点击了许愿按钮
                if wish_button.collidepoint(event.pos) and input_text.strip() and not wish_sent:
                    if send_to_wechat(input_text):
                        wish_sent = True
                
                # # 检查是否点击了返回按钮
                # if back_button.collidepoint(event.pos):
                #     reset_game()
    
    if game_active:
        # 玩家移动
        keys = pygame.key.get_pressed()
        if keys[K_LEFT] and player_rect.left > 0:
            player_rect.x -= player_speed
        if keys[K_RIGHT] and player_rect.right < WINDOW_WIDTH:
            player_rect.x += player_speed
        
        # 跳跃物理
        if is_jumping:
            player_rect.y += player_vel_y
            player_vel_y += gravity
            
            if player_rect.bottom >= WINDOW_HEIGHT - ground_height:
                player_rect.bottom = WINDOW_HEIGHT - ground_height
                is_jumping = False
                player_vel_y = 0
        
        # 移动障碍物
        for obstacle in obstacles[:]:
            obstacle['rect'].x -= obstacle_speed
            
            if player_rect.colliderect(obstacle['rect']):
                game_active = False
                game_over = True
            
            if obstacle['rect'].right < 0:
                obstacles.remove(obstacle)
        
        if player_rect.colliderect(flag_rect):
            game_active = False
            game_won = True
    
    # 绘制游戏元素
    draw_ground()
    draw_player()
    draw_obstacles()
    draw_flag()
    
    # 显示游戏状态
    if game_over:
        restart_button = show_game_over()
    elif game_won and not is_show_wishing_pool:
        wishing_pool_button = show_game_won()
    elif is_show_wishing_pool:
        back_button = show_wishing_pool()
    
    pygame.display.update()
    clock.tick(FPS)

pygame.quit()
sys.exit()