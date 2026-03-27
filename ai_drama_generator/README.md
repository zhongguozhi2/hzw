# AI短剧自动生成与拼接工具

基于 Seedance 2.0 API，输入完整剧情文本后自动：
1. 由大模型生成短剧分镜脚本（镜号、景别、运镜；默认不含旁白）
2. 拆分为 5 秒/段的视频片段与对应提示词
3. 逐段调用 API 生成视频，后续片段自动提取上一段最后一帧作为参考图
4. 全部生成后自动拼接、音频平滑过渡、添加字幕并发送到飞书

## 安装

```bash
cd ai_drama_generator
pip install -r requirements.txt
```

> 需要 Python 3.10+，以及系统安装 FFmpeg（moviepy 依赖）。

## 配置 API Key

只支持火山引擎 Ark（默认）

```bash
set VOLCENGINE_API_KEY=你的API密钥
```

## 使用

```bash
# 交互式输入剧情（输入完按两次回车）
python main.py --title "未命名短剧" --episode "第1集"

# 命令行直接传入
python main.py --story "男主在咖啡厅遇到女主，两人相视一笑，然后一起走出咖啡厅" --title "相遇咖啡馆" --episode "第1集"

# 从文件读取
python main.py --file story.txt --title "相遇咖啡馆" --episode "第2集"

# 预生成（不调用视频生成模型，但会输出 prompt.json）
python main.py --file story.txt --title "相遇咖啡馆" --episode "第2集" --mode pre

# 直接生成（调用视频生成模型）
python main.py --file story.txt --title "相遇咖啡馆" --episode "第2集" --mode direct

# 仅查看分镜，不调 API
python main.py --dry-run --story "男主在咖啡厅遇到女主，两人相视一笑" --title "相遇咖啡馆" --episode "第3集"

# 默认不生成旁白；如需旁白可开启
python main.py --file story.txt --title "相遇咖啡馆" --episode "第3集" --mode pre --with-narration

# 指定输出根目录（默认: D:\cbc\hzw\ai_drama_generator）
python main.py --story "..." --output "D:\cbc\hzw\ai_drama_generator" --title "相遇咖啡馆" --episode "第4集"

# 指定飞书 chat_id（默认: oc_64dd7b229c2a269377853397c575cc97）
python main.py --story "..." --title "相遇咖啡馆" --episode "第5集" --chat-id oc_xxx

# 仅生成，不发送飞书
python main.py --story "..." --title "相遇咖啡馆" --episode "第6集" --no-send

# 主角色/主场景（写入 剧名/role、剧名/scene），本集角色/场景（写入 剧名/集数/role、scene）；生成时合并主+本集一并传给模型
python main.py --file story.txt --title "相遇咖啡馆" --episode "第1集" ^
  --character-image "D:\refs\lead.png" --scene-image "D:\refs\cafe.jpg" ^
  --episode-character-image "D:\refs\ep1_guest.png" --episode-scene-image "D:\refs\ep1_room.jpg"

# 角色设定文本：主设定 → 剧名/role_design.txt，本集设定 → 剧名/集数/role_design.txt
python main.py --file story.txt --title "相遇咖啡馆" --episode "第1集" ^
  --role-design-file "D:\refs\main_role_design.txt" ^
  --episode-role-design-file "D:\refs\ep1_role_design.txt"
```

输出目录结构（示例）：

```text
D:\cbc\hzw\ai_drama_generator\相遇咖啡馆\
├── role_design.txt       # 全剧主角色设定（--role-design-file）
├── role\                 # 全剧主角色参考图（--character-image）
├── scene\                # 全剧主场景参考图（--scene-image）
└── 第1集\
    ├── role_design.txt   # 本集角色/本集表演设定（--episode-role-design-file）
    ├── role\             # 本集角色参考图（--episode-character-image）
    ├── scene\            # 本集场景参考图（--episode-scene-image）
    ├── story.txt
    ├── script.txt         # 唯一分镜脚本文件（默认不含旁白）
    ├── prompt.json       # 每次运行都会生成：提示词、参考图路径；直接生成时还会写入每段成片路径与最终成片路径
    ├── subtitle.txt
    ├── sub_video\
    │   ├── segment_000.mp4
    │   └── ...
    └── 相遇咖啡馆_第1集_20260324_113000.mp4
```

## 项目结构

```
ai_drama_generator/
├── main.py             # CLI 入口 & 主流程编排
├── config.py           # API 配置（环境变量驱动）
├── story_splitter.py   # LLM脚本生成 & 5秒分镜拆分
├── seedance_api.py     # Seedance 2.0 API 调用（提交/轮询/下载）
├── frame_extractor.py  # 提取视频最后一帧（OpenCV）
├── video_concat.py     # 视频拼接 & 音频渐变 & 字幕封装
├── send_file_to_feishu.py  # 飞书消息/文件发送
├── requirements.txt
└── README.md
```

## 注意事项

- 免费 API 每日有调用次数限制，请留意额度
- 每段视频时长为 5 秒，总耗时取决于分段数量
- 参考帧权重 `REFERENCE_STRENGTH` 可在 config.py 中调整（0.8-1.2）
- 视频 URL 有效期 24 小时，工具会自动下载并保存到 `sub_video` 目录
