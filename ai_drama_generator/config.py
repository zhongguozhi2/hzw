"""
Configuration for the AI Drama Generator.

This project uses the Volcengine Ark API (Seedance 2.0).
Set environment variables to configure API access.
"""

import os

# ─── Volcengine Ark API ────────────────────────────────────────────────────
VOLCENGINE_API_KEY = os.getenv("VOLCENGINE_API_KEY", "c6543db2-3235-4ab0-9b0c-f13337b2e5f0")
VOLCENGINE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
VOLCENGINE_MODEL = os.getenv("SEEDANCE_MODEL", "ep-20260325163922-kwsvs")
MULTI_REF_MODEL = os.getenv("MULTI_REF_MODEL", "ep-20260326162712-jmcsm")

# ─── Video Generation Parameters ───────────────────────────────────────────
VIDEO_QUALITY = "720p"      # 480p | 720p | 1080p
VIDEO_FPS = 24
ASPECT_RATIO = "16:9"       # 16:9 | 9:16 | 1:1
GENERATE_AUDIO = True
REFERENCE_STRENGTH = 1.0    # 0.8 – 1.2, higher = more faithful to reference
STORYBOARD_MODEL = os.getenv("STORYBOARD_MODEL", "ep-20260326113539-8v29x")


# ─── Polling ───────────────────────────────────────────────────────────────
POLL_INTERVAL = 8           # seconds between status checks
POLL_TIMEOUT = 600          # max wait per segment (10 min)

# ─── Retry ─────────────────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BACKOFF = 2           # exponential backoff multiplier

# ─── Derived helpers ───────────────────────────────────────────────────────

def get_api_key() -> str:
    key = VOLCENGINE_API_KEY
    if not key:
        raise ValueError(
            "未配置 API Key。请设置环境变量 VOLCENGINE_API_KEY"
        )
    return key


def get_base_url() -> str:
    return VOLCENGINE_BASE_URL
