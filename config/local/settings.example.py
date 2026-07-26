"""本地开发配置模板。

复制为同目录下的 ``settings.py``（已被 git 忽略），再按需修改。
``config/settings.py`` 会在启动时自动加载 ``config/local/settings.py`` 并覆盖同名配置项。
"""

# 独立前端本地开发（Vite 默认端口 5173）
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
