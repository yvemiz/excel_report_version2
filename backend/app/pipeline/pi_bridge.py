import os
import sys
import json
import shutil
import asyncio
import subprocess
import threading
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.config import settings

class PiAgentBridge:
    """
    Python 与 Node.js Pi-Agent 侧车智能体的 IPC 桥接适配器 (Route A 实现)
    职责：
    1. 动态探测系统 Node.js 运行环境与 pi-main 侧车脚本路径
    2. 将数据事实、单元格坐标与撰写指令序列化为标准 JSON 任务
    3. 唤起 Node.js Pi-Agent 子进程 (完美适配 Windows Proactor 与 Selector 双事件循环)
    4. 逐行反序列化 JSONL 事件流，向流水线和前端实时推送打字文本块
    """

    def __init__(self):
        self.node_path = shutil.which("node") or "node"
        bundled_sidecar = os.path.join(
            settings.BASE_DIR,
            "sidecar",
            "pi_agent_core_bundle.mjs"
        )
        legacy_sidecar = os.path.join(
            os.path.dirname(settings.BASE_DIR),
            "pi-main",
            "pi_agent_sidecar.mjs"
        )
        if os.path.exists(bundled_sidecar):
            self.sidecar_path = bundled_sidecar
        elif os.path.exists(legacy_sidecar):
            self.sidecar_path = legacy_sidecar
        else:
            self.sidecar_path = bundled_sidecar

    def is_available(self) -> bool:
        """检查 Node.js 运行环境与 Pi 侧车脚本是否就绪"""
        if not os.path.exists(self.sidecar_path):
            return False
        try:
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
        自动兼容 Windows SelectorEventLoop 与 ProactorEventLoop
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

        loop = asyncio.get_running_loop()
        use_threaded = sys.platform == "win32" and not isinstance(loop, getattr(asyncio, "ProactorEventLoop", type(None)))

        if use_threaded:
            async for item in self._stream_write_section_threaded(task_payload):
                yield item
            return

        try:
            proc = await asyncio.create_subprocess_exec(
                self.node_path,
                self.sidecar_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        except NotImplementedError:
            # SelectorEventLoop 降级兜底
            async for item in self._stream_write_section_threaded(task_payload):
                yield item
            return

        accumulated_text = ""
        done_event_yielded = False

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
                    event_type = event.get("type")

                    if event_type == "chunk":
                        chunk_text = event.get("text", "")
                        accumulated_text += chunk_text
                        yield {"type": "chunk", "text": chunk_text}

                    elif event_type in ("tool_execution_start", "tool_execution_end", "chart_generated", "agent_info"):
                        yield event

                    elif event_type == "done":
                        accumulated_text = event.get("full_content", accumulated_text)
                        done_event_yielded = True
                        yield {"type": "done", "full_content": accumulated_text}
                        break

                    elif event_type == "error":
                        print(f"[Pi-Agent Sidecar Error]: {event.get('message')}")

                except json.JSONDecodeError:
                    continue

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
            await asyncio.sleep(0.05)

    async def _stream_write_section_threaded(self, task_payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """为 Windows SelectorEventLoop 提供的多线程安全子进程管道"""
        proc = subprocess.Popen(
            [self.node_path, self.sidecar_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def reader():
            try:
                for line in proc.stdout:
                    loop.call_soon_threadsafe(q.put_nowait, line)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        # 写入任务数据
        proc.stdin.write(json.dumps(task_payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        proc.stdin.close()

        accumulated_text = ""
        done_event_yielded = False

        while True:
            line_str = await q.get()
            if line_str is None:
                break
            line_str = line_str.strip()
            if not line_str:
                continue

            try:
                event = json.loads(line_str)
                event_type = event.get("type")
                if event_type == "chunk":
                    chunk_text = event.get("text", "")
                    accumulated_text += chunk_text
                    yield {"type": "chunk", "text": chunk_text}
                elif event_type in ("tool_execution_start", "tool_execution_end", "chart_generated", "agent_info"):
                    yield event
                elif event_type == "done":
                    accumulated_text = event.get("full_content", accumulated_text)
                    done_event_yielded = True
                    yield {"type": "done", "full_content": accumulated_text}
                    break
                elif event_type == "error":
                    print(f"[Pi-Agent Sidecar Error]: {event.get('message')}")
            except json.JSONDecodeError:
                continue

        await asyncio.to_thread(proc.wait)
        if not done_event_yielded and accumulated_text:
            yield {"type": "done", "full_content": accumulated_text}

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

        loop = asyncio.get_running_loop()
        use_threaded = sys.platform == "win32" and not isinstance(loop, getattr(asyncio, "ProactorEventLoop", type(None)))

        if use_threaded:
            return await self._plan_outline_threaded(task_payload)

        try:
            proc = await asyncio.create_subprocess_exec(
                self.node_path,
                self.sidecar_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        except NotImplementedError:
            return await self._plan_outline_threaded(task_payload)

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

    async def _plan_outline_threaded(self, task_payload: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Windows SelectorEventLoop 兼容的大纲规划多线程调用"""
        proc = subprocess.Popen(
            [self.node_path, self.sidecar_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )
        out, _ = await asyncio.to_thread(proc.communicate, json.dumps(task_payload, ensure_ascii=False))
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "done" and "sections" in event:
                    return event["sections"]
                elif event.get("type") == "error":
                    print(f"[Pi-Agent Outline Error]: {event.get('message')}")
            except json.JSONDecodeError:
                continue
        return None
