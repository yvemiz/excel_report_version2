import unittest

from app.pipeline.dsml_guard import (
    DSML_MARK,
    DsmlLeakGate,
    contains_dsml,
    strip_dsml_tail,
)


class DsmlLeakGateTests(unittest.TestCase):
    def test_detects_marker_split_across_chunks(self):
        gate = DsmlLeakGate()
        safe = gate.push("<｜") + gate.push("｜DSML｜｜ calls>")
        self.assertEqual(safe, "")
        self.assertTrue(gate.leaked)
        self.assertEqual(gate.flush(), "")

    def test_keeps_safe_prefix_before_leak(self):
        gate = DsmlLeakGate()
        safe = gate.push("正文内容。\n")
        safe += gate.push("<｜｜DSML｜｜ calls>query_cell_lake")
        self.assertEqual(safe, "正文内容。\n")
        self.assertTrue(gate.leaked)
        self.assertNotIn(DSML_MARK, safe)

    def test_detects_marker_without_angle_prefix(self):
        gate = DsmlLeakGate()
        safe = gate.push("正文｜DS")
        safe += gate.push("ML｜ tail")
        self.assertEqual(safe, "正文")
        self.assertTrue(gate.leaked)

    def test_normal_fullwidth_pipe_is_not_held_or_blocked(self):
        gate = DsmlLeakGate()
        text = "A｜B｜C"
        safe = gate.push(text) + gate.flush()
        self.assertEqual(safe, text)
        self.assertFalse(gate.leaked)

    def test_trailing_lt_is_released_on_flush(self):
        gate = DsmlLeakGate()
        safe = gate.push("正常<") + gate.flush()
        self.assertEqual(safe, "正常<")
        self.assertFalse(gate.leaked)

    def test_full_dsml_only_round_yields_nothing(self):
        gate = DsmlLeakGate()
        safe = gate.push("<｜｜DSML｜｜ invoke name=\"x\">")
        self.assertEqual(safe, "")
        self.assertTrue(gate.leaked)
        self.assertEqual(gate.flush(), "")


class StripDsmlTailTests(unittest.TestCase):
    def test_removes_marker_and_everything_after(self):
        text = "这是正文。\n<｜｜DSML｜｜ calls>query_cell_lake</｜｜DSML｜｜ calls>"
        self.assertEqual(strip_dsml_tail(text), "这是正文。")

    def test_removes_marker_without_angle_prefix(self):
        text = "这是正文。\n｜DSML｜tail"
        self.assertEqual(strip_dsml_tail(text), "这是正文。")

    def test_keeps_normal_text_unchanged(self):
        text = "普通正文，没有工具调用标记。"
        self.assertEqual(strip_dsml_tail(text), text)
        self.assertFalse(contains_dsml(text))

    def test_detects_marker(self):
        self.assertTrue(contains_dsml("<｜｜DSML｜｜ calls>"))
        self.assertFalse(contains_dsml("普通正文"))


if __name__ == "__main__":
    unittest.main()

class FakeLeakingBridge:
    def is_available(self):
        return True

    async def stream_write_section(self, **kwargs):
        yield {"type": "chunk", "text": "### 2.1 测试章节\n\n<｜"}
        yield {"type": "chunk", "text": "｜DSML｜｜ calls>query_cell_lake"}
        yield {"type": "done", "full_content": "### 2.1 测试章节\n\n<｜｜DSML｜｜ calls>query_cell_lake"}


class AgentRunnerDsmlFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_pi_agent_leak_is_dropped_and_falls_back_without_marker(self):
        from app.pipeline.agent_runner import PiAgentRunner

        runner = PiAgentRunner(chart_service=object())
        runner.bridge = FakeLeakingBridge()
        runner.pi_bridge = runner.bridge
        runner.agent_mode = "pi_agent"
        runner.api_key = ""

        section_meta = {
            "chapter_title": "第二章 测试",
            "section_title": "2.1 测试章节",
            "objective": "验证 DSML 防线",
        }
        cell_mappings = [
            {
                "cell_id": "cell_test_1",
                "metric_path": "单位号",
                "raw_value": "0100",
                "file_name": "测试.xlsx",
                "sheet_name": "Sheet1",
            }
        ]
        events = []
        async for event in runner.stream_write_section(section_meta, {"data_points_count": 1}, cell_mappings):
            events.append(event)

        self.assertTrue(any(event.get("type") == "dsml_leak" for event in events))
        streamed_chunks = "".join(event.get("text", "") for event in events if event.get("type") == "chunk")
        done = next(event for event in events if event.get("type") == "done")
        self.assertNotIn(DSML_MARK, streamed_chunks)
        self.assertNotIn(DSML_MARK, done["full_content"])
        self.assertIn("测试章节", done["full_content"])
