import asyncio
from app.pipeline.pi_bridge import PiAgentBridge

async def test_pi_bridge_execution():
    bridge = PiAgentBridge()
    print(f"Node path: {bridge.node_path}")
    print(f"Sidecar path: {bridge.sidecar_path}")
    print(f"Bridge is available: {bridge.is_available()}")

    assert bridge.is_available(), "PiAgentBridge must be available"

    section_meta = {
        "chapter_title": "第一章 学校概况与办学定位",
        "section_title": "1.1 办学历史与发展目标",
        "objective": "客观阐述学校基础办学性质与办学规模"
    }
    retrieved_data = {"school": "海南师范大学", "type": "师范"}
    cell_mappings = [
        {"cell_id": "cell_001", "metric_path": "学校名称", "raw_value": "海南师范大学"},
        {"cell_id": "cell_002", "metric_path": "代码", "raw_value": "11658"},
        {"cell_id": "cell_003", "metric_path": "办学类型", "raw_value": "普通本科院校"},
        {"cell_id": "cell_004", "metric_path": "学校性质", "raw_value": "师范院校"}
    ]

    print("\n[*] Invoking Node.js Pi-Agent Sidecar via async subprocess...")
    chunks_received = 0
    full_text = ""

    async for event in bridge.stream_write_section(
        api_key="",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        section_meta=section_meta,
        retrieved_data=retrieved_data,
        cell_mappings=cell_mappings
    ):
        if event["type"] == "chunk":
            chunks_received += 1
            print(event["text"], end="", flush=True)
        elif event["type"] == "done":
            full_text = event["full_content"]
            print("\n\n[✓] Received done event from Pi-Agent!")

    print(f"\nTotal chunks: {chunks_received}")
    print(f"Total characters: {len(full_text)}")
    assert len(full_text) > 100
    assert "[^cell_001]" in full_text
    print("\n✅ Pi-Agent Bridge Route A verified successfully!")

async def test_pi_bridge_plan_outline():
    bridge = PiAgentBridge()
    catalog = [
        {"table_name": "tbl_base", "file_name": "表1-1 基本情况.xlsx", "sheet_name": "基本情况", "columns": ["学校名称", "办学类型"]},
        {"table_name": "tbl_custom", "file_name": "2024年科研创新与经费统计.xlsx", "sheet_name": "科研", "columns": ["项目数", "经费"]}
    ]
    sections = await bridge.plan_outline(
        api_key="",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        catalog=catalog,
        school_name="海南师范大学"
    )
    print(f"\n[*] Pi-Agent Outline Planner returned {len(sections)} sections:")
    for s in sections:
        print(f"  - {s['chapter_title']}: {s['section_title']} (绑表: {s['file_name']})")
    assert len(sections) == 2
    assert "学校概况" in sections[0]["chapter_title"]
    assert "科研创新" in sections[1]["chapter_title"]
    print("✅ Pi-Agent Outline Planning verified successfully!")

if __name__ == "__main__":
    async def main():
        await test_pi_bridge_execution()
        await test_pi_bridge_plan_outline()
    asyncio.run(main())
