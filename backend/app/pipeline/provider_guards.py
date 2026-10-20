"""厂商输出规则注册表。

主流程只使用 ``build_output_filters``，不直接依赖任何厂商规则。
新增模型厂商时，在这里注册对应 filter 即可。
"""

from __future__ import annotations

from typing import List

from app.pipeline.dsml_guard import DeepSeekDsmlFilter
from app.pipeline.output_guard import StreamLeakFilter


def is_deepseek(model: str, base_url: str = "") -> bool:
    text = f"{model or ''} {base_url or ''}".lower()
    return "deepseek" in text


def build_output_filters(model: str = "", base_url: str = "") -> List[StreamLeakFilter]:
    filters: List[StreamLeakFilter] = []
    if is_deepseek(model, base_url):
        filters.append(DeepSeekDsmlFilter())
    return filters
