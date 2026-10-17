import json
import asyncio
import logging
from typing import Literal, Optional
from urllib.parse import urlsplit
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from app.core.workspaces import Workspace, get_workspace, get_mutable_workspace, begin_operation

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline Execution"])

class ApiKeyConfig(BaseModel):
    api_key: str = Field(default="", max_length=8192)
    clear_api_key: bool = False
    base_url: str = Field(default="https://api.deepseek.com", max_length=2048)
    model: str = Field(default="deepseek-chat", min_length=1, max_length=200)
    agent_mode: Literal["pi_agent", "python_native"] = "pi_agent"

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value):
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("请填写有效的 HTTP(S) 服务根地址")
        return value

    @field_validator("api_key", "model")
    @classmethod
    def validate_text(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("配置不能包含控制字符")
        return value.strip()


@router.get("/config")
def get_llm_config(workspace: Workspace = Depends(get_workspace)):
    config = workspace.auth.load_config(workspace.user_id)
    return {key: value for key, value in config.items() if key != "api_key"} | {"has_api_key": bool(config["api_key"])}

@router.post("/config")
async def update_llm_config(cfg: ApiKeyConfig, workspace: Workspace = Depends(get_mutable_workspace)):
    """更新大模型配置 (如在前端配置 DeepSeek API Key 及智能体驱动引擎)"""
    saved = workspace.auth.load_config(workspace.user_id)
    config = {
        "api_key": "" if cfg.clear_api_key else (cfg.api_key or saved["api_key"]),
        "base_url": cfg.base_url, "model": cfg.model, "agent_mode": cfg.agent_mode,
    }
    workspace.auth.save_config(workspace.user_id, config)
    workspace.apply_config(config)
    mode_name = "Pi-Agent 侧车智能体模式 (Node.js)" if cfg.agent_mode == "pi_agent" else "Python 原生极速模式"
    return {"success": True, "has_api_key": bool(config["api_key"]), "message": f"配置已保存，当前引擎：{mode_name}"}

@router.get("/status")
async def get_pipeline_status(workspace: Workspace = Depends(get_workspace)):
    """获取当前流水线执行状态与已生成的报告小节"""
    return workspace.snapshot()

@router.get("/stream")
async def pipeline_sse(school_name: Optional[str] = None, resume: bool = False, workspace: Workspace = Depends(get_workspace)):
    """SSE 流式事件接口（完美兼容各种浏览器与代理环境）"""
    if not workspace.cell_lake.count():
        raise HTTPException(status_code=400, detail="请先上传当前账号的 Excel 报表")
    begin_operation(workspace)
    async def event_generator():
        try:
            async for event in workspace.pipeline.execute_pipeline(school_name=school_name, resume=resume):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)
        except Exception:
            logging.getLogger(__name__).exception("Report generation failed for user %s", workspace.user_id)
            yield 'data: {"type":"error","message":"报告生成失败，请查看后端运行日志"}\n\n'
        finally:
            workspace.pipeline.save_checkpoint()
            workspace.operation_lock.release()
    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.websocket("/ws")
async def pipeline_websocket(websocket: WebSocket, workspace: Workspace = Depends(get_workspace)):
    """流水线实时流式执行与监控 WebSocket"""
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            action = data.get("action")

            if action == "start":
                req_school = data.get("school_name")
                if not workspace.cell_lake.count() or not workspace.operation_lock.acquire(blocking=False):
                    await websocket.send_json({"type": "error", "message": "请先导入数据并等待当前任务结束"})
                    continue
                try:
                    async for event in workspace.pipeline.execute_pipeline(school_name=req_school, resume=bool(data.get("resume", False))):
                        await websocket.send_text(json.dumps(event, ensure_ascii=False))
                        await asyncio.sleep(0.01)
                finally:
                    workspace.pipeline.save_checkpoint()
                    workspace.operation_lock.release()

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
async def get_deepseek_balance(workspace: Workspace = Depends(get_workspace)):
    """实时查询 DeepSeek API 余额与 Token 消耗统计 (Inspired by pi-deepseek-balance)"""
    from app.core.telemetry_service import DeepSeekBalanceMonitor
    return await DeepSeekBalanceMonitor.fetch_balance(
        workspace.pipeline.agent_runner.api_key, trace_file=workspace.pipeline.telemetry_file,
    )

@router.get("/telemetry")
async def get_pipeline_telemetry(workspace: Workspace = Depends(get_workspace)):
    """获取全链路可观测性时延、Token与Jev质检得分汇总"""
    from app.core.telemetry_service import TelemetryService
    return TelemetryService.get_summary(trace_file=workspace.pipeline.telemetry_file)
