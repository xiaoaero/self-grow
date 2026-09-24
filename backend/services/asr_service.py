"""
Self Grow — ASR 服务（DashScope paraformer 实时语音识别）

封装 dashscope SDK 的 Recognition 类，将同步回调模式桥接到 async 世界。
浏览器 → WebSocket → send_audio_frame() → DashScope SDK
DashScope SDK → callback.on_event() → Queue → async 轮询 → WebSocket 推送
"""

import os
import queue
import logging
import threading

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from config import DASHSCOPE_API_KEY

log = logging.getLogger(__name__)

# DashScope WebSocket 地址（可通过环境变量配置）
DASHSCOPE_WS_URL = os.getenv(
    "DASHSCOPE_WS_URL",
    "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
)

# ⚠️ 建立连接时的互斥锁 —— 这把锁是**必要的**，不要删。
#
# 背景：`dashscope.api_key` 与 `dashscope.base_websocket_api_url` 是**模块级全局**，
# 而 `Recognition` 实例建立连接时会去读这两个全局值（SDK 没有提供实例级参数，
# 已经查过 `Recognition.__init__` 的签名确认了）。
#
# 于是多用户并发使用时，后启动的会话会把前一个的 key 覆盖掉 ——
# A 的语音识别可能实际用的是 B 的密钥（本项目支持每个用户在
# 「用户中心 → 模型信息」里配自己的 ASR key，所以这不是假想问题）。
#
# 这把锁保证「设置全局 → 建立连接」这一段是**原子**的。临界区里没有 await，
# 锁的持有时间就是建连耗时（百毫秒级），可以接受。
_dashscope_start_lock = threading.Lock()


class ASRCallback(RecognitionCallback):
    """ASR 回调：将识别结果和状态变化放入队列（线程安全）"""

    def __init__(self, result_queue: queue.Queue, state_queue: queue.Queue):
        self.result_queue = result_queue
        self.state_queue = state_queue

    def on_open(self) -> None:
        log.info("ASR WebSocket 连接已建立")
        self.state_queue.put({"type": "open"})

    def on_close(self) -> None:
        log.info("ASR WebSocket 连接已关闭")
        self.state_queue.put({"type": "close"})

    def on_complete(self) -> None:
        log.info("ASR 识别完成")
        self.state_queue.put({"type": "complete"})

    def on_error(self, message) -> None:
        log.error(f"ASR 错误: {message.message}")
        self.state_queue.put({"type": "error", "message": str(message.message)})

    def on_event(self, result: RecognitionResult) -> None:
        """收到实时识别结果"""
        sentence = result.get_sentence()
        if sentence and 'text' in sentence:
            text = sentence['text']
            is_end = RecognitionResult.is_sentence_end(sentence)
            self.result_queue.put({
                "text": text,
                "is_end": is_end,
            })


class ASRConnection:
    """
    管理一个 DashScope paraformer 实时语音识别会话。

    用法:
        asr = ASRConnection()
        asr.start()
        asr.send_audio(pcm_bytes)  # 多次调用
        result = asr.get_result()  # 非阻塞获取
        asr.stop()
    """

    def __init__(self, model="paraformer-realtime-v2", sample_rate=16000, user_id=None):
        # 动态读取启用 ASR 配置（model_configs 表，无配置则回退参数/.env）
        from db.model_configs import get_active_config
        cfg = get_active_config(user_id or 1, "asr")
        self.model = (cfg or {}).get("model") or model
        self.api_key = (cfg or {}).get("api_key") or DASHSCOPE_API_KEY
        self.base_url = (cfg or {}).get("base_url") or DASHSCOPE_WS_URL
        self.sample_rate = sample_rate
        self.recognition = None
        self.result_queue = queue.Queue()
        self.state_queue = queue.Queue()

    def start(self):
        """启动 ASR 识别会话（建立 WebSocket 连接，**同步阻塞**）

        ⚠️ 会阻塞到建连完成，async 上下文里请用 `await asyncio.to_thread(asr.start)`。
        """
        if not self.api_key:
            raise RuntimeError("ASR API Key 未设置，无法使用语音识别")

        # 创建回调
        callback = ASRCallback(self.result_queue, self.state_queue)

        # 创建 Recognition 实例
        self.recognition = Recognition(
            model=self.model,
            format='pcm',
            sample_rate=self.sample_rate,
            semantic_punctuation_enabled=True,
            callback=callback,
        )

        # ⚠️「设置全局 key/url → 建立连接」必须在同一把锁里完成。
        #    中间被别的会话插进来就会「串号」：本会话实际用上别人的密钥。
        #    详见文件顶部 `_dashscope_start_lock` 的说明。
        with _dashscope_start_lock:
            dashscope.api_key = self.api_key
            dashscope.base_websocket_api_url = self.base_url
            # start() 会建立 WebSocket 连接并在后台线程运行
            self.recognition.start()

        log.info(f"ASR 识别会话已启动: model={self.model}")

    def send_audio(self, data: bytes):
        """发送音频分片到 DashScope（线程安全）"""
        if self.recognition:
            self.recognition.send_audio_frame(data)

    def get_result(self):
        """非阻塞获取一条识别结果，没有则返回 None"""
        try:
            return self.result_queue.get_nowait()
        except queue.Empty:
            return None

    def get_state(self):
        """非阻塞获取一条状态变化，没有则返回 None"""
        try:
            return self.state_queue.get_nowait()
        except queue.Empty:
            return None

    @property
    def is_running(self):
        return self.recognition is not None

    def stop(self):
        """停止 ASR 识别会话"""
        if self.recognition:
            try:
                self.recognition.stop()
            except Exception as e:
                log.warning(f"ASR stop 异常: {e}")
            self.recognition = None
            log.info("ASR 识别会话已停止")