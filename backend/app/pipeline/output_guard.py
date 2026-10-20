"""模型输出守卫的通用框架。

主流程不依赖任何厂商协议；厂商特有规则以 ``StreamLeakFilter`` 插件形式注册。
目前由 ``provider_guards`` 根据 model/base_url 选择规则。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Iterable, Protocol, Sequence, Tuple


class ModelOutputLeakError(RuntimeError):
    """模型输出被守卫规则判定为不可用。"""

    def __init__(self, filter_name: str, message: str):
        super().__init__(message)
        self.filter_name = filter_name
        self.message = message


class StreamLeakFilter(Protocol):
    name: str
    message: str

    @property
    def leaked(self) -> bool: ...

    def push(self, text: str) -> str: ...

    def flush(self) -> str: ...

    def sanitize(self, text: str) -> Tuple[str, bool]: ...


class StreamGuardChain:
    """按顺序组合多个厂商规则。"""

    def __init__(self, filters: Sequence[StreamLeakFilter]):
        self.filters = list(filters)
        self.leaked = False
        self.leaked_filter_name = ""
        self.leaked_message = ""

    def _mark(self, item: StreamLeakFilter) -> None:
        self.leaked = True
        self.leaked_filter_name = item.name
        self.leaked_message = item.message

    def push(self, text: str) -> str:
        if self.leaked:
            return ""
        safe = text or ""
        for item in self.filters:
            if item.leaked:
                self._mark(item)
                return ""
            safe = item.push(safe)
            if item.leaked:
                self._mark(item)
                return ""
        return safe

    def flush(self) -> str:
        if self.leaked:
            return ""
        safe = ""
        for item in self.filters:
            safe = item.push(safe) + item.flush()
            if item.leaked:
                self._mark(item)
                return ""
        return safe

    def sanitize(self, text: str) -> Tuple[str, bool]:
        clean = text or ""
        for item in self.filters:
            clean, leaked = item.sanitize(clean)
            if leaked:
                self._mark(item)
                return clean, True
        return clean, False


async def guard_content_stream(
    events: AsyncIterator[Dict[str, Any]],
    filters: Iterable[StreamLeakFilter],
) -> AsyncIterator[Dict[str, Any]]:
    """把任意厂商的 chunk/done 事件流包装成统一的安全事件流。

    非文本事件原样透传。检测到泄漏时先发出 ``model_output_leak``，
    让 UI 清空已流出的前缀，再抛出 ``ModelOutputLeakError`` 交由上层回退。
    """
    chain = StreamGuardChain(list(filters))

    async for event in events:
        kind = event.get("type")
        if kind == "chunk":
            safe_text = chain.push(event.get("text", ""))
            if safe_text:
                yield {**event, "text": safe_text}
            if chain.leaked:
                yield {
                    "type": "model_output_leak",
                    "filter": chain.leaked_filter_name,
                    "message": chain.leaked_message,
                }
                raise ModelOutputLeakError(chain.leaked_filter_name, chain.leaked_message)
        elif kind == "done":
            raw_content = event.get("full_content", "")
            clean, leaked = chain.sanitize(raw_content)
            if leaked:
                yield {
                    "type": "model_output_leak",
                    "filter": chain.leaked_filter_name,
                    "message": chain.leaked_message,
                }
                raise ModelOutputLeakError(chain.leaked_filter_name, chain.leaked_message)
            tail = chain.flush()
            if tail:
                yield {"type": "chunk", "text": tail}
            yield {**event, "full_content": clean}
            return
        else:
            yield event

    if chain.leaked:
        raise ModelOutputLeakError(chain.leaked_filter_name, chain.leaked_message)
    tail = chain.flush()
    if tail:
        yield {"type": "chunk", "text": tail}


def sanitize_model_output(
    text: str,
    filters: Iterable[StreamLeakFilter],
) -> Tuple[str, bool, str]:
    """落库/导出边界使用的同步兜底，返回 ``(clean, leaked, message)``。"""
    chain = StreamGuardChain(list(filters))
    clean, leaked = chain.sanitize(text)
    return clean, leaked, chain.leaked_message
