"""
Telemetry & DeepSeek Balance Monitoring Service
Inspired by pi-deepseek-balance and local structured observability traces.
Provides:
1. Local JSONL structured trace recording for every section and pipeline turn
2. Real-time DeepSeek API balance inquiry and CNY cost burn-rate estimation
3. Full-system telemetry metrics aggregation (tokens, latencies, Jev scores)
"""

import os
import time
import json
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings

class TelemetryService:
    """
    全链路流水线与智能体可观测性追踪服务
    记录每个章节撰写的时延、Subagent角色、Token开销与Jev质检得分
    """

    TRACE_FILE = os.path.join(settings.BASE_DIR, "data", "telemetry_traces.jsonl")

    @classmethod
    def record_section_trace(
        cls,
        section_id: str,
        section_title: str,
        subagent_role: str,
        duration_ms: float,
        prompt_tokens: int,
        completion_tokens: int,
        jev_score: float,
        citations_count: int,
        audit_passed: bool
    ) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(cls.TRACE_FILE), exist_ok=True)

        # DeepSeek 标准计费估算（人民币）：输入 1元/百万Token，输出 4元/百万Token
        est_cost_cny = round((prompt_tokens * 1.0 + completion_tokens * 4.0) / 1_000_000, 5)

        trace_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "section_id": section_id,
            "section_title": section_title,
            "subagent_role": subagent_role,
            "duration_ms": round(duration_ms, 1),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "est_cost_cny": est_cost_cny,
            "jev_score": jev_score,
            "citations_count": citations_count,
            "audit_passed": audit_passed
        }

        try:
            with open(cls.TRACE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Telemetry Warning]: 无法写入本地可观测跟踪文件: {e}")

        return trace_entry

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """获取近期生成的聚合可观测性指标"""
        if not os.path.exists(cls.TRACE_FILE):
            return {
                "total_sections_traced": 0,
                "total_tokens_consumed": 0,
                "total_cost_cny": 0.0,
                "avg_duration_sec": 0.0,
                "recent_traces": []
            }

        traces = []
        try:
            with open(cls.TRACE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        traces.append(json.loads(line))
        except Exception:
            pass

        total_sections = len(traces)
        total_tokens = sum(t.get("total_tokens", 0) for t in traces)
        total_cost = sum(t.get("est_cost_cny", 0.0) for t in traces)
        avg_dur = (sum(t.get("duration_ms", 0.0) for t in traces) / max(1, total_sections)) / 1000.0

        return {
            "total_sections_traced": total_sections,
            "total_tokens_consumed": total_tokens,
            "total_cost_cny": round(total_cost, 4),
            "avg_duration_sec": round(avg_dur, 2),
            "recent_traces": traces[-15:]  # 返回最近 15 条
        }


class DeepSeekBalanceMonitor:
    """
    DeepSeek API 账户余额与 Token 消耗速率实时监控器
    支持向 DeepSeek 官方查询实时账户余额 (CNY)，并测算实时烧钱速率
    """

    @classmethod
    async def fetch_balance(cls, api_key: Optional[str] = None) -> Dict[str, Any]:
        key = api_key or getattr(settings, "DEEPSEEK_API_KEY", "")
        if not key or key.startswith("your_") or len(key) < 10:
            return {
                "is_configured": False,
                "balance_cny": "--",
                "currency": "CNY",
                "status": "未配置真实 DeepSeek API Key（当前使用高保真确定性引擎）",
                "token_burn_summary": TelemetryService.get_summary()
            }

        url = "https://api.deepseek.com/user/balance"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {key}"
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    # 官方结构形如：{"is_available": true, "balance_infos": [{"currency": "CNY", "total_balance": "88.50"}]}
                    balance_infos = data.get("balance_infos", [])
                    cny_info = next((b for b in balance_infos if b.get("currency") == "CNY"), None)
                    cny_val = cny_info.get("total_balance", "--") if cny_info else "--"
                    return {
                        "is_configured": True,
                        "is_available": data.get("is_available", True),
                        "balance_cny": cny_val,
                        "currency": "CNY",
                        "status": "余额正常" if data.get("is_available") else "余额不足或受限",
                        "token_burn_summary": TelemetryService.get_summary()
                    }
                else:
                    return {
                        "is_configured": True,
                        "balance_cny": "--",
                        "status": f"查询接口响应 HTTP {resp.status_code}",
                        "token_burn_summary": TelemetryService.get_summary()
                    }
        except Exception as e:
            return {
                "is_configured": True,
                "balance_cny": "--",
                "status": f"查询超时或离线 ({str(e)})",
                "token_burn_summary": TelemetryService.get_summary()
            }
