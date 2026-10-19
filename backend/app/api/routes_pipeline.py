import json
import asyncio
import logging
from typing import Literal, Optional
from urllib.parse import urlsplit
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
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

@router.post("/outline")
async def plan_report_outline(
    school_name: Optional[str] = None,
    dataset_id: Optional[str] = Query(None),
    workspace: Workspace = Depends(get_workspace),
):
    """只规划大纲并保存为待确认报告版本，不进入正文生成。"""
    dataset = workspace.dataset(dataset_id)
    if not dataset.cell_lake.count():
        raise HTTPException(status_code=400, detail="请先为当前数据集上传 Excel 报表")
    detected_school = dataset.cell_lake.detect_school_metadata().get("school_name", "").strip()
    configured_school = workspace.school_name.strip()
    if detected_school and configured_school and detected_school != configured_school:
        raise HTTPException(
            status_code=409,
            detail=f"当前批次数据识别为“{detected_school}”，与学校配置“{configured_school}”不一致，请切换到正确批次",
        )

    begin_operation(workspace)
    report = None
    try:
        report = dataset.create_report(school_name=school_name or configured_school, status="outline_running")
        outline = await report.pipeline.plan_outline_only(school_name=report.pipeline.custom_school_name)
        report.mark_status("outline_ready")
        return {
            "dataset_id": dataset.dataset_id,
            "report_version_id": report.report_version_id,
            "outline": outline,
            "outline_audit": report.pipeline.outline_jev_audit,
            "quality_summary": report.pipeline.quality_summary(),
        }
    except HTTPException:
        if report is not None:
            report.mark_status("failed", "大纲规划失败")
        raise
    except Exception as exc:
        if report is not None:
            report.mark_status("failed", str(exc))
        logging.getLogger(__name__).exception("Outline planning failed for user %s", workspace.user_id)
        raise HTTPException(status_code=500, detail="大纲规划失败，请查看后端运行日志") from exc
    finally:
        workspace.operation_lock.release()

@router.get("/status")
async def get_pipeline_status(dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_workspace)):
    """获取当前数据集最新报告版本的执行状态与章节结果"""
    return workspace.snapshot(dataset_id)

@router.get("/stream")
async def pipeline_sse(
    school_name: Optional[str] = None,
    resume: bool = False,
    skip_outline: bool = False,
    report_version_id: Optional[str] = Query(None),
    dataset_id: Optional[str] = Query(None),
    workspace: Workspace = Depends(get_workspace),
):
    """SSE 流式事件接口；每次新生成创建独立的报告版本，不覆盖旧版本。"""
    dataset = workspace.dataset(dataset_id)
    if not dataset.cell_lake.count():
        raise HTTPException(status_code=400, detail="请先为当前数据集上传 Excel 报表")
    detected_school = dataset.cell_lake.detect_school_metadata().get("school_name", "").strip()
    configured_school = workspace.school_name.strip()
    if detected_school and configured_school and detected_school != configured_school:
        raise HTTPException(
            status_code=409,
            detail=f"当前批次数据识别为“{detected_school}”，与学校配置“{configured_school}”不一致，请切换到正确批次",
        )

    begin_operation(workspace)
    try:
        report = None
        if report_version_id:
            report = dataset.get_report(report_version_id)
            if report.version.get("status") == "completed":
                raise HTTPException(status_code=409, detail="该报告版本已完成；请重新规划大纲后再生成")
        elif resume:
            latest = dataset.latest_report()
            if latest and latest.version.get("status") != "completed":
                report = latest
        if report is None:
            report = dataset.create_report(school_name=school_name or workspace.school_name, status="running")
        use_existing_outline = bool(skip_outline or report.pipeline.sections_plan)
        if skip_outline and not report.pipeline.sections_plan:
            raise HTTPException(status_code=400, detail="该报告版本没有可复用的大纲，请先规划大纲")
    except Exception:
        workspace.operation_lock.release()
        raise
    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'report_started', 'dataset_id': dataset.dataset_id, 'report_version_id': report.report_version_id}, ensure_ascii=False)}\n\n"
            async for event in report.pipeline.execute_pipeline(
                school_name=school_name,
                resume=resume,
                use_existing_outline=use_existing_outline,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)
            report.mark_status("completed" if report.pipeline.current_stage >= 5 else "interrupted")
        except Exception as exc:
            logging.getLogger(__name__).exception("Report generation failed for user %s", workspace.user_id)
            report.mark_status("failed", str(exc))
            yield 'data: {"type":"error","message":"报告生成失败，请查看后端运行日志"}\n\n'
        finally:
            report.pipeline.save_checkpoint()
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
                dataset = workspace.dataset(data.get("dataset_id"))
                if not dataset.cell_lake.count() or not workspace.operation_lock.acquire(blocking=False):
                    await websocket.send_json({"type": "error", "message": "请先导入数据并等待当前任务结束"})
                    continue
                detected_school = dataset.cell_lake.detect_school_metadata().get("school_name", "").strip()
                configured_school = workspace.school_name.strip()
                if detected_school and configured_school and detected_school != configured_school:
                    workspace.operation_lock.release()
                    await websocket.send_json({
                        "type": "error",
                        "message": f"当前批次数据识别为“{detected_school}”，与学校配置“{configured_school}”不一致",
                    })
                    continue
                report = None
                if bool(data.get("resume", False)):
                    latest = dataset.latest_report()
                    if latest and latest.version.get("status") != "completed":
                        report = latest
                if report is None:
                    report = dataset.create_report(school_name=req_school or workspace.school_name, status="running")
                try:
                    await websocket.send_text(json.dumps({
                        "type": "report_started", "dataset_id": dataset.dataset_id,
                        "report_version_id": report.report_version_id,
                    }, ensure_ascii=False))
                    async for event in report.pipeline.execute_pipeline(school_name=req_school, resume=bool(data.get("resume", False))):
                        await websocket.send_text(json.dumps(event, ensure_ascii=False))
                        await asyncio.sleep(0.01)
                    report.mark_status("completed" if report.pipeline.current_stage >= 5 else "interrupted")
                finally:
                    report.pipeline.save_checkpoint()
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
async def get_deepseek_balance(dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_workspace)):
    """实时查询 DeepSeek API 余额与 Token 消耗统计 (Inspired by pi-deepseek-balance)"""
    from app.core.telemetry_service import DeepSeekBalanceMonitor
    report = workspace.dataset(dataset_id).latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="当前数据集还没有报告版本")
    return await DeepSeekBalanceMonitor.fetch_balance(
        report.pipeline.agent_runner.api_key, trace_file=report.pipeline.telemetry_file,
    )

@router.get("/telemetry")
async def get_pipeline_telemetry(dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_workspace)):
    """获取全链路可观测性时延、Token与Jev质检得分汇总"""
    from app.core.telemetry_service import TelemetryService
    report = workspace.dataset(dataset_id).latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="当前数据集还没有报告版本")
    return TelemetryService.get_summary(trace_file=report.pipeline.telemetry_file)
