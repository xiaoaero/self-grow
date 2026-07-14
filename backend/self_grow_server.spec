# -*- mode: python ; coding: utf-8 -*-
"""Self Grow — PyInstaller 打包配置"""

import os

block_cipher = None

BACKEND_DIR = os.path.abspath('.')

a = Analysis(
    ['self_grow_server.py'],
    pathex=[BACKEND_DIR],
    binaries=[],
    datas=[
        # AI 提示词模板（Python 模块，需要被找到）
        ('prompts', 'prompts'),
    ],
    hiddenimports=[
        # uvicorn 内部模块
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # APScheduler
        'apscheduler.schedulers.asyncio',
        'apscheduler.triggers.cron',
        'apscheduler.triggers.base',
        'apscheduler.executors.pool',
        'apscheduler.executors.base',
        # LangChain
        'langchain_openai',
        'langchain_core',
        'langchain_core.messages',
        'langchain_core.language_models',
        'langchain_core.runnables',
        # HTTP 依赖
        'httpx',
        'h11',
        'anyio',
        'sniffio',
        # dotenv
        'dotenv',
        # Python 标准库
        'sqlite3',
        # FastAPI 依赖
        'pydantic',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.staticfiles',
        'starlette.responses',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型库以减小体积
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='self-grow-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='self-grow-backend',
)
