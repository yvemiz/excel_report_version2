import urllib.request
import json
import time
import sys

def main():
    print("==================================================")
    print("🚀 实时运行项目全链路: 数据摄入 -> SSE 流水线 -> 质检 -> 成果物导出")
    print("==================================================")
    
    print("\n[Step 1] 请求 /api/load_example_data (摄入 8 个高等教育状态数据报表)...")
    req = urllib.request.Request(
        'http://127.0.0.1:8008/api/load_example_data',
        data=b'',
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print(f"  ✓ {res.get('message')}")
        print(f"  ✓ 当前 Cell Lake 物理单元格总数: {res.get('total_cells')}")

    print("\n[Step 2] 实时监听 /api/pipeline/stream (SSE 流式五阶段任务)...")
    start_time = time.time()
    req_sse = urllib.request.Request(
        'http://127.0.0.1:8008/api/pipeline/stream?school_name=%E6%B5%B7%E5%8D%97%E5%B8%88%E8%8C%83%E5%A4%A7%E5%AD%A6'
    )

    event_count = 0
    with urllib.request.urlopen(req_sse) as resp:
        while True:
            line = resp.readline()
            if not line:
                break
            line_str = line.decode('utf-8').strip()
            if line_str.startswith('data: '):
                event_count += 1
                try:
                    data = json.loads(line_str[6:])
                except Exception:
                    continue

                etype = data.get('type')
                if etype == 'stage_update':
                    stage_id = data.get('stage_id')
                    status = data.get('status')
                    print(f"  [Stage {stage_id}] 状态更新: {status.upper()}")
                    if stage_id == 1 and status == 'completed':
                        outline = data.get('data', {}).get('outline', [])
                        jev_audit = data.get('data', {}).get('jev_audit', {})
                        print(f"    ↳ Jev大纲裁决分: {jev_audit.get('structure_score')} (批准: {jev_audit.get('approved')})")
                        print(f"    ↳ 自适应规划生成 {len(outline)} 个深度剖析小节")
                    elif stage_id == 5 and status == 'completed':
                        export_files = data.get('data', {}).get('export_files', {})
                        total_words = data.get('data', {}).get('total_words')
                        reconcil = data.get('data', {}).get('total_reconciliation_points')
                        print("\n[Step 3] 🎉 流水线执行收官，生成成果物：")
                        print(f"  📄 Word 质检研报: {export_files.get('docx')}")
                        print(f"  📊 Excel 穿透对账表: {export_files.get('xlsx')}")
                        print(f"  📝 报告总字数: {total_words} 字")
                        print(f"  🔍 物理溯源审计点: {reconcil} 处")
                        print(f"  🌐 Word 下载接口: http://127.0.0.1:8008{export_files.get('docx_url')}")
                        print(f"  🌐 Excel 下载接口: http://127.0.0.1:8008{export_files.get('xlsx_url')}")
                elif etype == 'section_stage':
                    sec_id = data.get('section_id')
                    stg = data.get('stage')
                    txt = data.get('text', '')
                    if stg == 'retrieved':
                        print(f"    ↳ [{sec_id}] Stage 2: 零Token数据检索完成 ({data.get('points_count')} 个数据指标)")
                    elif stg == 'writing':
                        print(f"    ↳ [{sec_id}] Stage 3: 流式撰写中...")
                    elif stg == 'audited':
                        aud = data.get('audit', {})
                        pass_rate = aud.get('audit_res', {}).get('pass_rate')
                        jev_score = aud.get('jev_res', {}).get('logic_score')
                        print(f"    ✔ [{sec_id}] Stage 4: 质检放行！吻合率={pass_rate}%, Jev逻辑分={jev_score}")
                elif etype == 'section_chart':
                    sec_id = data.get('section_id')
                    cfile = data.get('chart', {}).get('file_name')
                    print(f"    📊 [{sec_id}] 动态统计图表已渲染: {cfile}")

    elapsed = time.time() - start_time
    print(f"\n==================================================")
    print(f"⚡ 实时运行圆满成功！耗时: {elapsed:.2f} 秒，累计接收 SSE 响应包: {event_count} 次")
    print("==================================================")

if __name__ == '__main__':
    main()
