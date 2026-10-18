"""DSML 泄漏防线。

DSML 是 DeepSeek 模型内部的工具调用标记语言（形如 ``<｜｜DSML｜｜tool_calls>``，
其中竖线为全角 U+FF5C）。正常情况下厂商服务端会把标记解析成结构化 tool_calls；
偶发畸形标记会从 content 通道原样透传，导致正文出现内部协议文本，并且该轮
tool_calls 为空、模型原本要执行的检索被跳过。

判据：全角竖线 + ``DSML`` 的组合 ``｜DSML｜`` 在正常中文回答中不会出现。
"""

from __future__ import annotations


DSML_MARK = "｜DSML｜"

DSML_LEAK_MESSAGE = "检测到模型工具调用标记（DSML）泄漏，已丢弃本轮输出并重新生成"

# 疑似片段最大扣留长度。标记头 ``<｜｜DSML｜｜`` 不足 10 字符，32 给足冗余；
# 攒满仍凑不出判据，说明只是普通正文里的全角竖线（表格排版等），原样放行。
HOLD_MAX = 32


class DsmlLeakError(RuntimeError):
    """模型工具调用标记从正文通道泄漏。"""


class DsmlLeakGate:
    """流式泄漏门。

    正文增量先过闸再下发。见到全角竖线先扣住，后续增量拼上后：

    - 凑出 ``｜DSML｜``：判定泄漏，此后不再放行任何内容；
    - 攒到 ``HOLD_MAX`` 仍凑不出：原样放行，避免误伤普通文本。

    每轮生成创建新实例，状态不跨轮。
    """

    def __init__(self) -> None:
        self.held = ""
        self.leaked = False

    def push(self, text: str) -> str:
        """喂入一段正文增量，返回可安全下发的部分。"""
        if self.leaked:
            return ""

        work = self.held + (text or "")
        self.held = ""
        out: list[str] = []

        while True:
            index = work.find("｜")
            if index < 0:
                # 结尾悬着的 < 可能是标记头 <｜ 被分片切断的前半个，先扣住。
                if work.endswith("<"):
                    self.held = "<"
                    return "".join(out) + work[:-1]
                return "".join(out) + work

            # 标记头形如 <｜｜DSML｜｜：紧邻竖线的 < 属于标记的一部分。
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

            # 攒满仍没有判据：这个竖线属于普通正文，放行后继续扫描。
            out.append(rest[0])
            work = rest[1:]

    def flush(self) -> str:
        """流结束时调用：未定性的扣留内容不是泄漏，原样放行。"""
        rest = "" if self.leaked else self.held
        self.held = ""
        return rest


def strip_dsml_tail(text: str) -> str:
    """落库前兜底剥离。

    从判据处向前吃掉所有紧邻的标记头字符（``｜`` 与 ``<``），再截掉自标记
    起的整段尾巴。工具标记只会出现在正文末尾，模型转入调用后不会再回来补充
    正文，因此保留前半段安全内容。
    """
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
