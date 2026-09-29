import json
import asyncio
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.pipeline.stages import ReportPipeline
from app.config import settings

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline Execution"])

pipeline_instance: ReportPipeline = None

def init_pipeline_routes(pipe: ReportPipeline):
    global pipeline_instance
    pipeline_instance = pipe

class ApiKeyConfig(BaseModel):
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    agent_mode: str = "pi_agent"  # "pi_agent" (Node.js 侧车模式) 或 "python_native"

@router.post("/config")
async def update_llm_config(cfg: ApiKeyConfig):
    """更新大模型配置 (如在前端配置 DeepSeek API Key 及智能体驱动引擎)"""
    pipeline_instance.agent_runner.set_api_key(cfg.api_key)
    pipeline_instance.agent_runner.base_url = cfg.base_url
    pipeline_instance.agent_runner.model = cfg.model
    pipeline_instance.agent_runner.set_agent_mode(cfg.agent_mode)
    pipeline_instance.jev_judge.api_key = cfg.api_key
    pipeline_instance.jev_judge.base_url = cfg.base_url
    pipeline_instance.jev_judge.model = cfg.model
    mode_name = "Pi-Agent 侧车智能体模式 (Node.js)" if cfg.agent_mode == "pi_agent" else "Python 原生极速模式"
    return {"success": True, "message": f"已更新模型配置，当前引擎：{mode_name}"}

@router.get("/status")
async def get_pipeline_status():
    """获取当前流水线执行状态与已生成的报告小节"""
    return {
        "current_stage": pipeline_instance.current_stage,
        "stages": pipeline_instance.stages_info,
        "sections_plan": pipeline_instance.sections_plan,
        "generated_sections": pipeline_instance.generated_sections,
        "export_files": pipeline_instance.export_files
    }

@router.get("/stream")
async def pipeline_sse(school_name: Optional[str] = None, resume: bool = False):
    """SSE 流式事件接口（完美兼容各种浏览器与代理环境，支持断点续存恢复）"""
    async def event_generator():
        async for event in pipeline_instance.execute_pipeline(school_name=school_name, resume=resume):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.websocket("/ws")
async def pipeline_websocket(websocket: WebSocket):
    """流水线实时流式执行与监控 WebSocket"""
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            action = data.get("action")

            if action == "start":
                req_school = data.get("school_name")
                # 触发五阶段流水线
                async for event in pipeline_instance.execute_pipeline(school_name=req_school):
                    await websocket.send_text(json.dumps(event, ensure_ascii=False))
                    await asyncio.sleep(0.01)

            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass

@router.get("/balance")
async def get_deepseek_balance():
    """实时查询 DeepSeek API 余额与 Token 消耗统计 (Inspired by pi-deepseek-balance)"""
    from app.core.telemetry_service import DeepSeekBalanceMonitor
    api_key = pipeline_instance.agent_runner.api_key if pipeline_instance and hasattr(pipeline_instance, "agent_runner") else ""
    return await DeepSeekBalanceMonitor.fetch_balance(api_key)

@router.get("/telemetry")
async def get_pipeline_telemetry():
    """获取全链路可观测性时延、Token与Jev质检得分汇总"""
    from app.core.telemetry_service import TelemetryService
    return TelemetryService.get_summary()
