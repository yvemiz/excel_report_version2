import json
import asyncio
from typing import Dict, Any, List
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

@router.post("/config")
async def update_llm_config(cfg: ApiKeyConfig):
    """更新大模型配置 (如在前端配置 DeepSeek API Key)"""
    pipeline_instance.agent_runner.set_api_key(cfg.api_key)
    pipeline_instance.agent_runner.base_url = cfg.base_url
    pipeline_instance.agent_runner.model = cfg.model
    pipeline_instance.jev_judge.api_key = cfg.api_key
    pipeline_instance.jev_judge.base_url = cfg.base_url
    pipeline_instance.jev_judge.model = cfg.model
    return {"success": True, "message": "已更新模型配置"}

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
async def pipeline_sse():
    """SSE 流式事件接口（完美兼容各种浏览器与代理环境）"""
    async def event_generator():
        async for event in pipeline_instance.execute_pipeline():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
                # 触发五阶段流水线
                async for event in pipeline_instance.execute_pipeline():
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
