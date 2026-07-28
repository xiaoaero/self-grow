"""
Self Grow — ASR 服务（DashScope paraformer 实时语音识别）

封装 dashscope SDK 的 Recognition 类，将同步回调模式桥接到 async 世界。
浏览器 → WebSocket → send_audio_frame() → DashScope SDK
DashScope SDK → callback.on_event() → Queue → async 轮询 → WebSocket 推送
"""

import os
import queue
import logging

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from config import DASHSCOPE_API_KEY

log = logging.getLogger(__name__)

# DashScope WebSocket 地址（可通过环境变量配置）
DASHSCOPE_WS_URL = os.getenv(
    "DASHSCOPE_WS_URL",
    "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
)


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

    def __init__(self, model="paraformer-realtime-v2", sample_rate=16000):
        self.model = model
        self.sample_rate = sample_rate
        self.recognition = None
        self.result_queue = queue.Queue()
        self.state_queue = queue.Queue()

    def start(self):
        """启动 ASR 识别会话（建立 WebSocket 连接）"""
        if not DASHSCOPE_API_KEY:
            raise RuntimeError("DASHSCOPE_API_KEY 未设置，无法使用语音识别")

        # 配置 DashScope
        dashscope.api_key = DASHSCOPE_API_KEY
        dashscope.base_websocket_api_url = DASHSCOPE_WS_URL

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