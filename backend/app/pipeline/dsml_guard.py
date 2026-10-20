"""DeepSeek DSML 泄漏规则。

DSML 是 DeepSeek 模型内部的工具调用标记语言（形如 ``<｜｜DSML｜｜tool_calls>``，
其中竖线为全角 U+FF5C）。该规则只处理 DeepSeek 特有的标记，作为
``StreamLeakFilter`` 插入通用守卫链，不进入主流程。
"""

from __future__ import annotations

from typing import Tuple


DSML_MARK = "｜DSML｜"

DSML_LEAK_MESSAGE = "检测到模型工具调用标记（DSML）泄漏，已丢弃本轮输出并重新生成"

# 疑似片段最大扣留长度。标记头 ``<｜｜DSML｜｜`` 不足 10 字符，32 给足冗余；
# 攒满仍凑不出判据，说明只是普通正文里的全角竖线（表格排版等），原样放行。
HOLD_MAX = 32


class DsmlLeakGate:
    """DSML 流式泄漏门。"""

    def __init__(self) -> None:
        self.held = ""
        self.leaked = False

    def push(self, text: str) -> str:
        if self.leaked:
            return ""

        work = self.held + (text or "")
        self.held = ""
        out: list[str] = []

        while True:
            index = work.find("｜")
            if index < 0:
                if work.endswith("<"):
                    self.held = "<"
                    return "".join(out) + work[:-1]
                return "".join(out) + work

            if index > 0 and work[index - 1] == "<":
                index -= 1

            out.append(work[:index])
            rest = work[index:]

            if DSML_MARK in rest:
                self.leaked = True
                return "".join(out)

            if len(rest) < HOLD_MAX:
                self.held = rest
                return "".join(out)

            out.append(rest[0])
            work = rest[1:]

    def flush(self) -> str:
        rest = "" if self.leaked else self.held
        self.held = ""
        return rest


def strip_dsml_tail(text: str) -> str:
    """剥离从 DSML 判据开始的整段尾巴。"""
    value = text or ""
    index = value.find(DSML_MARK)
    if index < 0:
        return value

    cut = index
    while cut > 0 and value[cut - 1] in ("｜", "<"):
        cut -= 1
    return value[:cut].rstrip()


def contains_dsml(text: str) -> bool:
    return DSML_MARK in (text or "")


class DeepSeekDsmlFilter:
    """DeepSeek DSML 的 ``StreamLeakFilter`` 实现。"""

    name = "deepseek_dsml"
    message = DSML_LEAK_MESSAGE

    def __init__(self) -> None:
        self._gate = DsmlLeakGate()

    @property
    def leaked(self) -> bool:
        return self._gate.leaked

    def push(self, text: str) -> str:
        return self._gate.push(text)

    def flush(self) -> str:
        return self._gate.flush()

    def sanitize(self, text: str) -> Tuple[str, bool]:
        leaked = contains_dsml(text)
        return (strip_dsml_tail(text) if leaked else (text or "")), leaked
