/**
 * Self Grow — SSE（Server-Sent Events）读取工具
 *
 * 独立文件、零依赖，主应用（index.html）与技能树独立应用（skill-tree/index.html）
 * 共用同一份实现 —— 两边都通过 `js/auth.js` 包装过 `window.fetch`，
 * 所以这里的请求会自动带上 `Authorization: Bearer`。
 *
 * ================================================================
 * ⚠️ 为什么不用浏览器原生的 EventSource
 *
 *   1. `EventSource` **不能自定义请求头** —— 本项目身份靠
 *      `Authorization: Bearer <token>`，用 EventSource 必然 401。
 *      它也只能发 GET，而后端流式端点需要 POST 传请求体。
 *   2. `EventSource` 会自动重连（断线就重发请求），
 *      对「每次调用都真的花钱跑一次 LLM」的端点来说这个行为很危险。
 *
 * 所以用 `fetch` + `resp.body.getReader()` 自己解析。代价是要手工做分块拼接
 * （一个 SSE 事件可能被 TCP 切成好几次 read），下面已经处理好了。
 *
 * ================================================================
 * 事件协议（与后端 services/sse.py 一一对应）
 *
 *   data: {"type":"stage","stage":"routing","label":"正在理解你的意图…"}
 *   data: {"type":"token","text":"已"}
 *   data: {"type":"error","message":"..."}
 *   data: {"type":"done", ...完整结果...}
 *
 *   冒号开头的是心跳注释行（`: ping`），只为保活，无数据。
 */

(function (global) {
    'use strict';

    /**
     * 以流式方式请求一个 SSE 端点
     *
     * @param {string} url 完整 URL 或 /api/... 相对路径
     * @param {object} [body] 请求体（会被 JSON 序列化）
     * @param {object} [handlers]
     * @param {function} [handlers.onStage] 收到阶段事件：({stage, label, ...})
     * @param {function} [handlers.onToken] 收到文本增量：('已')
     * @param {function} [handlers.onComment] 收到心跳（一般不用管，留作日志）
     * @param {function} [handlers.onError] 收到服务端的 error 事件
     * @param {object} [options] {signal, headers, method}
     *
     * @returns {Promise<object>} `done` 事件的完整内容
     *
     * @throws {Error} HTTP 非 2xx（带 .status）、服务端 error 事件、
     *                 或流意外结束（没收到 done）
     */
    async function streamSSE(url, body, handlers, options) {
        handlers = handlers || {};
        options = options || {};

        var onStage = handlers.onStage || function () {};
        var onToken = handlers.onToken || function () {};
        var onComment = handlers.onComment || function () {};
        var onError = handlers.onError || function () {};

        var init = {
            method: options.method || 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, options.headers || {}),
        };
        if (body !== undefined && body !== null) init.body = JSON.stringify(body);
        if (options.signal) init.signal = options.signal;

        var resp = await fetch(url, init);

        // 流还没开始就失败（401 / 404 / 400 …）→ 仍然走正常的 HTTP 错误路径，
        // 这样调用方能用 .status 区分（技能树那边就是靠 404 判断会话失效的）
        if (!resp.ok) {
            var detail = 'HTTP ' + resp.status;
            try {
                var errBody = await resp.json();
                if (errBody && errBody.detail) detail = errBody.detail;
            } catch (e) { /* 响应体不是 JSON，忽略 */ }
            var httpErr = new Error(detail);
            httpErr.status = resp.status;
            throw httpErr;
        }

        if (!resp.body || typeof resp.body.getReader !== 'function') {
            throw new Error('当前浏览器不支持流式响应（fetch 的 body.getReader 不可用）');
        }

        var reader = resp.body.getReader();
        var decoder = new TextDecoder('utf-8');
        var buffer = '';
        var donePayload = null;
        var streamError = null;

        try {
            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;

                buffer += decoder.decode(chunk.value, { stream: true });

                // 一个事件以「空行」结束；buffer 里可能同时有完整事件和半截事件，
                // 半截的留在 buffer 里等下次 read 补齐。
                // ⚠️ 分隔符只按 "\n\n" 找（服务端固定写 \n）；CRLF 的兼容放在逐行解析时
                // 去掉行尾 \r —— 不能在 buffer 上直接 replace，因为一个 "\r" 可能
                // 落在本次分块末尾、它后面的 "\n" 在下一个分块里，提前处理会漏掉
                var sep;
                while ((sep = buffer.indexOf('\n\n')) !== -1) {
                    var raw = buffer.slice(0, sep);
                    buffer = buffer.slice(sep + 2);

                    var dataLines = [];
                    var isComment = false;
                    raw.split('\n').forEach(function (line) {
                        if (line.charAt(line.length - 1) === '\r') line = line.slice(0, -1);
                        if (line.charAt(0) === ':') { isComment = true; return; }
                        if (line.indexOf('data:') === 0) dataLines.push(line.slice(5).trim());
                    });

                    if (dataLines.length === 0) {
                        if (isComment) onComment();
                        continue;
                    }

                    var payload;
                    try {
                        payload = JSON.parse(dataLines.join('\n'));
                    } catch (e) {
                        // 解析不了的整条跳过，不要让一条坏事件打断整个流
                        console.warn('SSE 事件解析失败（已跳过）:', raw.slice(0, 200));
                        continue;
                    }

                    if (payload.type === 'token') onToken(payload.text || '');
                    else if (payload.type === 'stage') onStage(payload);
                    else if (payload.type === 'error') {
                        streamError = new Error(payload.message || '服务端处理失败');
                        // 打标：调用方据此区分「服务端给了明确原因」和「纯粹连不上」
                        streamError.fromStream = true;
                        onError(streamError);
                    } else if (payload.type === 'done') donePayload = payload;
                }
            }
        } finally {
            // 正常结束或抛异常都要释放读取锁，否则后续请求可能被浏览器排队
            try { reader.releaseLock(); } catch (e) { /* 忽略 */ }
        }

        if (streamError) throw streamError;
        if (!donePayload) throw new Error('连接中断：没有收到结束事件（done）');
        return donePayload;
    }

    global.streamSSE = streamSSE;
})(window);
