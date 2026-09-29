import os
import json
import shutil
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.config import settings

class PiAgentBridge:
    """
    Python 与 Node.js Pi-Agent 侧车智能体的 IPC 桥接适配器 (Route A 实现)
    职责：
    1. 动态探测系统 Node.js 运行环境与 pi-main 侧车脚本路径
    2. 将数据事实、单元格坐标与撰写指令序列化为标准 JSON 任务
    3. 异步唤起 Node.js Pi-Agent 子进程 (stdio 管道通信)
    4. 逐行反序列化 JSONL 事件流，向流水线和前端实时推送打字文本块
    """

    def __init__(self):
        self.node_path = shutil.which("node") or "node"
        self.sidecar_path = os.path.join(
            os.path.dirname(settings.BASE_DIR),
            "pi-main",
            "pi_agent_sidecar.mjs"
        )

    def is_available(self) -> bool:
        """检查 Node.js 运行环境与 Pi 侧车脚本是否就绪"""
        if not os.path.exists(self.sidecar_path):
            return False
        try:
            # 快速验证 Node.js 是否可正常运行
            return bool(shutil.which(self.node_path) or os.path.exists(self.node_path))
        except Exception:
            return False

    async def stream_write_section(
        self,
        api_key: str,
        base_url: str,
        model: str,
        section_meta: Dict[str, Any],
        retrieved_data: Dict[str, Any],
        cell_mappings: List[Dict[str, Any]],
        revision_feedback: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        通过异步子进程调用 Node.js Pi-Agent 智能体
        """
        if not self.is_available():
            raise RuntimeError(f"Pi-Agent 运行环境未就绪 (侧车脚本不存在或 Node 缺失: {self.sidecar_path})")

        task_payload = {
            "action": "write_section",
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "section_meta": section_meta,
            "retrieved_data": retrieved_data,
            "cell_mappings": cell_mappings,
            "revision_feedback": revision_feedback
        }

        # 启动 Node.js 子进程
        proc = await asyncio.create_subprocess_exec(
            self.node_path,
            self.sidecar_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        accumulated_text = ""
        done_event_yielded = False

        try:
            # 写入任务数据并关闭输入流
            input_bytes = json.dumps(task_payload, ensure_ascii=False).encode("utf-8")
            if proc.stdin:
                proc.stdin.write(input_bytes)
                await proc.stdin.drain()
                proc.stdin.close()

            # 读取 stdout 实时流式事件
            while True:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break

                line_str = line_bytes.decode("utf-8", errors="ignore").strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                    event_type = event.get("type")

                    if event_type == "chunk":
                        chunk_text = event.get("text", "")
                        accumulated_text += chunk_text
                        yield {"type": "chunk", "text": chunk_text}

                    elif event_type == "done":
                        accumulated_text = event.get("full_content", accumulated_text)
                        done_event_yielded = True
                        yield {"type": "done", "full_content": accumulated_text}
                        break

                    elif event_type == "error":
                        print(f"[Pi-Agent Sidecar Error]: {event.get('message')}")

                except json.JSONDecodeError:
                    continue

            # 等待子进程退出
            try:
                await proc.wait()
            except Exception:
                pass

            if not done_event_yielded:
                if accumulated_text:
                    yield {"type": "done", "full_content": accumulated_text}
                else:
                    stderr_out = await proc.stderr.read() if proc.stderr else b""
                    err_msg = stderr_out.decode("utf-8", errors="ignore")
                    raise RuntimeError(f"Pi-Agent 退出未产生正文，错误信息: {err_msg}")
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            # 确保 Windows Proactor EventLoop 清理管道
            await asyncio.sleep(0.05)

    async def plan_outline(
        self,
        api_key: str,
        base_url: str,
        model: str,
        catalog: List[Dict[str, Any]],
        school_name: str = ""
    ) -> Optional[List[Dict[str, Any]]]:
        """
        通过异步子进程调用 Node.js Pi-Agent 智能体规划大纲与章节拓扑
        """
        if not self.is_available():
            return None

        task_payload = {
            "action": "plan_outline",
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "catalog": catalog,
            "school_name": school_name
        }

        proc = await asyncio.create_subprocess_exec(
            self.node_path,
            self.sidecar_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        planned_sections = None

        try:
            input_bytes = json.dumps(task_payload, ensure_ascii=False).encode("utf-8")
            if proc.stdin:
                proc.stdin.write(input_bytes)
                await proc.stdin.drain()
                proc.stdin.close()

            while True:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break

                line_str = line_bytes.decode("utf-8", errors="ignore").strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                    if event.get("type") == "done" and "sections" in event:
                        planned_sections = event["sections"]
                        break
                    elif event.get("type") == "error":
                        print(f"[Pi-Agent Outline Error]: {event.get('message')}")
                except json.JSONDecodeError:
                    continue

            try:
                await proc.wait()
            except Exception:
                pass

        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            await asyncio.sleep(0.05)

        return planned_sections
