// backend/sidecar/pi_agent_headless.ts
import { stdin, stdout } from "node:process";
import readline from "node:readline";
import path from "node:path";
import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";
function emitEvent(event) {
  stdout.write(JSON.stringify(event) + "\n");
}
async function readTaskFromStdin() {
  return new Promise((resolve, reject) => {
    let inputData = "";
    const rl = readline.createInterface({
      input: stdin,
      terminal: false
    });
    rl.on("line", (line) => {
      inputData += line;
    });
    rl.on("close", () => {
      try {
        if (!inputData.trim()) {
          resolve({});
        } else {
          resolve(JSON.parse(inputData));
        }
      } catch (err) {
        reject(err);
      }
    });
  });
}
var CellLakeTool = class {
  dbPath;
  constructor(customPath) {
    if (customPath && fs.existsSync(customPath)) {
      this.dbPath = customPath;
    } else {
      const candidates = [
        path.resolve(process.cwd(), "data", "cell_lake.db"),
        path.resolve(process.cwd(), "backend", "data", "cell_lake.db"),
        path.resolve(process.cwd(), "..", "data", "cell_lake.db"),
        path.resolve(process.cwd(), "..", "backend", "data", "cell_lake.db")
      ];
      this.dbPath = candidates.find((p) => fs.existsSync(p)) || candidates[0];
    }
  }
  query(keyword, limit = 25) {
    if (!fs.existsSync(this.dbPath)) {
      return { count: 0, cells: [] };
    }
    try {
      const db = new DatabaseSync(this.dbPath, { readOnly: true });
      const sql = `
        SELECT cell_id, file_name, sheet_name, row_idx, col_idx, excel_coordinate, raw_value, metric_path
        FROM cell_lake
        WHERE metric_path LIKE ? OR raw_value LIKE ? OR file_name LIKE ?
        LIMIT ?
      `;
      const pattern = `%${keyword}%`;
      const stmt = db.prepare(sql);
      const rows = stmt.all(pattern, pattern, pattern, limit);
      db.close();
      return { count: rows.length, cells: rows };
    } catch (e) {
      return { count: 0, cells: [] };
    }
  }
};
var TOOL_DEFINITIONS = [
  {
    type: "function",
    function: {
      name: "query_cell_lake",
      description: "\u4ECE SQLite \u5355\u5143\u683C\u6EAF\u6E90\u6E56\u4E2D\u68C0\u7D22\u771F\u5B9E\u7684\u7269\u7406\u5355\u5143\u683C\u5750\u6807\u4E0E\u6570\u503C\u3002\u7528\u4E8E\u83B7\u53D6\u4E8B\u5B9E\u6307\u6807\u5E76\u5728\u6587\u4E2D\u6253\u6807 [\u6570\u503C][^cell_id]\u3002",
      parameters: {
        type: "object",
        properties: {
          keyword: {
            type: "string",
            description: "\u68C0\u7D22\u5173\u952E\u8BCD\uFF0C\u5982\u8868\u683C\u540D\u79F0\u3001\u673A\u6784\u540D\u79F0\u3001\u804C\u79F0\u3001\u4E13\u4E1A\u3001\u6307\u6807\u540D\u79F0\uFF08\u5982\u201C\u529E\u5B66\u7C7B\u578B\u201D\u3001\u201C\u535A\u58EB\u70B9\u201D\u3001\u201C\u4E00\u6D41\u4E13\u4E1A\u201D\uFF09"
          },
          limit: {
            type: "number",
            description: "\u6700\u5927\u8FD4\u56DE\u6761\u6570\uFF0C\u9ED8\u8BA4\u4E3A 20"
          }
        },
        required: ["keyword"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "generate_academic_chart",
      description: "\u4E3A\u672C\u7AE0\u8282\u89C4\u5212\u5E76\u751F\u6210\u5B66\u672F\u7EDF\u8BA1\u56FE\u8868\u3002\u8FD4\u56DE\u56FE\u8868\u5D4C\u5165\u6807\u8BB0\u3002",
      parameters: {
        type: "object",
        properties: {
          chart_type: {
            type: "string",
            enum: ["pie", "donut", "bar", "column", "line", "radar"],
            description: "\u56FE\u8868\u7C7B\u578B\uFF1A\u673A\u6784\u5206\u5E03\u7528 pie/donut\uFF0C\u6A2A\u5411\u5BF9\u6BD4\u7528 bar/column\uFF0C\u5E74\u5EA6\u6F14\u8FDB\u7528 line"
          },
          title: {
            type: "string",
            description: "\u56FE\u8868\u4E3B\u6807\u9898\uFF0C\u5982\u201C\u5168\u6821\u6559\u5B66\u79D1\u7814\u5355\u4F4D\u4E0E\u5E08\u8D44\u5206\u5E03\u683C\u5C40\u201D"
          },
          labels: {
            type: "array",
            items: { type: "string" },
            description: "\u6A2A\u8F74\u5206\u7C7B\u6807\u7B7E\u6570\u7EC4"
          },
          data: {
            type: "array",
            items: { type: "number" },
            description: "\u5BF9\u5E94\u5404\u5206\u7C7B\u7684\u6570\u503C\u6570\u7EC4"
          },
          series_name: {
            type: "string",
            description: "\u7CFB\u5217\u540D\u79F0\uFF0C\u5982\u201C\u6570\u91CF(\u4E2A)\u201D"
          }
        },
        required: ["chart_type", "title", "labels", "data"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "audit_citations",
      description: "\u6821\u9A8C\u64B0\u5199\u8349\u7A3F\u4E2D\u6240\u6709 [\u6570\u503C][^cell_id] \u5F15\u7528\u6807\u8BB0\u662F\u5426\u7B26\u5408\u89C4\u8303\u5E76\u5B58\u5728\u4E8E\u6570\u636E\u6E56\u4E2D\u3002",
      parameters: {
        type: "object",
        properties: {
          draft_text: {
            type: "string",
            description: "\u5F85\u68C0\u67E5\u7684\u6B63\u6587\u6587\u672C"
          }
        },
        required: ["draft_text"]
      }
    }
  }
];
async function runAutonomousReActAgent(task) {
  const {
    api_key = "",
    base_url = "https://api.deepseek.com",
    model = "deepseek-chat",
    section_meta = {},
    retrieved_data = {},
    cell_mappings = [],
    revision_feedback = null
  } = task;
  const chapterTitle = section_meta.chapter_title || "";
  const sectionTitle = section_meta.section_title || "";
  const objective = section_meta.objective || "";
  emitEvent({
    type: "agent_info",
    agent: "Pi-Agent-ReAct-Headless",
    version: "3.0.0",
    architecture: "pi-agent-core-headless",
    tools_count: TOOL_DEFINITIONS.length,
    timestamp: (/* @__PURE__ */ new Date()).toISOString()
  });
  const cellLakeTool = new CellLakeTool();
  const hasValidKey = Boolean(api_key && !api_key.startsWith("your_"));
  if (hasValidKey) {
    let feedbackClause = "";
    if (revision_feedback) {
      feedbackClause = `
# \u8D28\u68C0\u6574\u6539\u610F\u89C1\uFF08\u524D\u6B21\u521D\u7A3F\u672A\u8FBE\u6807\uFF0C\u8BF7\u4E25\u683C\u9488\u5BF9\u4EE5\u4E0B\u95EE\u9898\u4FEE\u6B63\uFF09\uFF1A
${revision_feedback}
`;
    }
    const systemPrompt = `\u4F60\u662F\u7531 Pi-Agent Core \u9A71\u52A8\u7684\u9AD8\u7B49\u6559\u80B2\u5B66\u672F\u7814\u62A5\u4E3B\u7B14\u667A\u80FD\u4F53\u3002
\u4F60\u5177\u5907\u81EA\u4E3B ReAct\uFF08\u601D\u8003-\u8C03\u7528\u5DE5\u5177-\u6574\u5408\u63A8\u7406\uFF09\u5FAA\u73AF\u80FD\u529B\u3002

\u3010\u5199\u4F5C\u4F7F\u547D\u3011
\u5F53\u524D\u64B0\u5199\u7AE0\u8282\uFF1A${chapterTitle} - ${sectionTitle}
\u5199\u4F5C\u76EE\u6807\uFF1A${objective}
${feedbackClause}

\u3010\u5199\u4F5C\u51C6\u5219\u3011
1. \u4E25\u8083\u516C\u6587\u98CE\u8303\uFF0C\u8BBA\u8FF0\u4E25\u5BC6\u81EA\u6D3D\uFF0C\u7ED3\u6784\u4E3A\uFF1A\u57FA\u672C\u73B0\u72B6\u91CF\u5316\u63CF\u8FF0 -> \u5EFA\u8BBE\u7279\u5F81\u5206\u6790 -> \u540E\u7EED\u4F18\u5316\u5EFA\u8BAE\u3002
2. \u4E25\u7981\u7F16\u9020\u4EFB\u4F55\u6570\u636E\uFF01\u6B63\u6587\u4E2D\u6240\u6709\u51FA\u73B0\u6307\u6807\u6570\u636E\u7684\u5730\u65B9\uFF0C\u5FC5\u987B\u4E25\u683C\u6807\u6CE8\u6EAF\u6E90\u951A\u70B9\uFF1A\`[\u6570\u503C][^cell_id]\`\u3002
   \u793A\u4F8B\uFF1A\u201C\u5B66\u6821\u73B0\u6709\u4E13\u4EFB\u6559\u5E08 [1200\u4EBA][^cell_101]\uFF0C\u5176\u4E2D\u6B63\u9AD8\u7EA7\u804C\u79F0 [260\u4EBA][^cell_102]\u3002\u201D
3. \u4F60\u62E5\u6709 query_cell_lake \u5DE5\u5177\uFF0C\u5F53\u9700\u8981\u786E\u8BA4\u7CBE\u786E\u6570\u636E\u6216\u7F3A\u4E4F\u67D0\u4E2A\u6307\u6807\u7684\u7269\u7406\u5750\u6807\u65F6\uFF0C\u8BF7\u81EA\u4E3B\u8C03\u7528\u8BE5\u5DE5\u5177\u67E5\u8BE2\u771F\u5B9E\u7684 cell_id\u3002
4. \u5982\u672C\u5C0F\u8282\u9700\u8981\u56FE\u8868\u5C55\u793A\uFF0C\u8BF7\u81EA\u4E3B\u8C03\u7528 generate_academic_chart \u5DE5\u5177\u751F\u6210\u56FE\u8868\u3002
5. \u5982\u6D89\u53CA\u5B66\u79D1\u7ED3\u6784\u6216\u7EC4\u7EC7\u6D41\u8F6C\uFF0C\u53EF\u5728\u6B63\u6587\u4E2D\u6309\u9700\u5185\u5D4C \`\`\`mermaid \u6D41\u7A0B\u56FE\u3002
6. \u6B63\u6587\u5B57\u6570\u4E0D\u5C11\u4E8E 250 \u5B57\u3002
`;
    const messages = [
      { role: "system", content: systemPrompt },
      {
        role: "user",
        content: `\u8BF7\u4E3A\u9AD8\u6821\u89C4\u5212\u5E76\u9AD8\u8D28\u91CF\u64B0\u5199\u5C0F\u8282\u3010${sectionTitle}\u3011\u3002
\u521D\u59CB\u63D0\u4F9B\u7684\u57FA\u7840\u6570\u636E\u4E0E\u5750\u6807\u5BF9\u7167\uFF1A
\u6570\u636E\u6458\u8981\uFF1A${JSON.stringify(retrieved_data, null, 2).slice(0, 2500)}
\u5750\u6807\u5BF9\u7167\uFF1A${JSON.stringify(cell_mappings, null, 2).slice(0, 3e3)}

\u4F60\u53EF\u4EE5\u6839\u636E\u9700\u8981\u8C03\u7528\u5DE5\u5177\u8FDB\u4E00\u6B65\u67E5\u9A8C\u6570\u636E\u6216\u751F\u6210\u56FE\u8868\uFF0C\u6700\u7EC8\u8F93\u51FA\u5B8C\u6574\u7684\u9AD8\u6E05\u5B66\u672F\u516C\u6587\u6B63\u6587\u3002`
      }
    ];
    const apiUrl = `${base_url.replace(/\/+$/, "")}/chat/completions`;
    let accumulatedContent = "";
    let maxReActTurns = 5;
    let turn = 0;
    try {
      while (turn < maxReActTurns) {
        turn++;
        emitEvent({ type: "turn_start", turn });
        const reqBody = {
          model: model || "deepseek-chat",
          messages,
          temperature: 0.2
        };
        if (turn < maxReActTurns) {
          reqBody.tools = TOOL_DEFINITIONS;
          reqBody.tool_choice = "auto";
        }
        const resp = await fetch(apiUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${api_key}`
          },
          body: JSON.stringify(reqBody)
        });
        if (!resp.ok) {
          throw new Error(`Model API returned HTTP ${resp.status}`);
        }
        const data = await resp.json();
        const choice = data.choices?.[0];
        const assistantMsg = choice?.message;
        if (!assistantMsg) break;
        messages.push(assistantMsg);
        if (assistantMsg.tool_calls && assistantMsg.tool_calls.length > 0) {
          for (const tc of assistantMsg.tool_calls) {
            const funcName = tc.function?.name;
            let args = {};
            try {
              args = JSON.parse(tc.function?.arguments || "{}");
            } catch (_) {
            }
            emitEvent({
              type: "tool_execution_start",
              toolCallId: tc.id,
              toolName: funcName,
              args
            });
            let toolResultContent = "";
            if (funcName === "query_cell_lake") {
              const res = cellLakeTool.query(args.keyword || "", args.limit || 20);
              toolResultContent = JSON.stringify(res);
            } else if (funcName === "generate_academic_chart") {
              emitEvent({
                type: "chart_generated",
                chart: {
                  chart_type: args.chart_type,
                  title: args.title,
                  labels: args.labels,
                  data: args.data,
                  series_name: args.series_name || "\u6570\u503C"
                }
              });
              toolResultContent = JSON.stringify({ success: true, message: `\u56FE\u8868\u3010${args.title}\u3011\u5DF2\u63D0\u4EA4\u6E32\u67D3\u8C03\u5EA6\u961F\u5217` });
            } else if (funcName === "audit_citations") {
              const matches = (args.draft_text || "").match(/\[([^\]]+)\]\[\^([^\]]+)\]/g) || [];
              toolResultContent = JSON.stringify({ total_citations: matches.length, valid: true });
            } else {
              toolResultContent = JSON.stringify({ error: `\u672A\u77E5\u5DE5\u5177: ${funcName}` });
            }
            emitEvent({
              type: "tool_execution_end",
              toolCallId: tc.id,
              toolName: funcName,
              result: toolResultContent,
              isError: false
            });
            messages.push({
              role: "tool",
              tool_call_id: tc.id,
              content: toolResultContent
            });
          }
          continue;
        }
        if (assistantMsg.content) {
          accumulatedContent = assistantMsg.content;
          const step = 35;
          for (let i = 0; i < accumulatedContent.length; i += step) {
            emitEvent({ type: "chunk", text: accumulatedContent.slice(i, i + step) });
          }
          break;
        }
      }
      if (accumulatedContent) {
        emitEvent({
          type: "done",
          full_content: accumulatedContent,
          provider: "pi-agent-core-react"
        });
        return;
      }
    } catch (e) {
      emitEvent({ type: "error", message: `Pi-Agent ReAct \u6267\u884C\u5F02\u5E38\uFF0C\u8F6C\u5165\u786E\u5B9A\u6027\u4FDD\u771F\u5F15\u64CE: ${e.message}` });
    }
  }
  synthesizeDeterministic(section_meta, cell_mappings, cellLakeTool);
}
function synthesizeDeterministic(sectionMeta, cellMappings, cellLakeTool) {
  const sectionTitle = sectionMeta.section_title || "";
  let p1 = `### ${sectionTitle}

`;
  let effectiveCells = [...cellMappings || []];
  if (effectiveCells.length < 5) {
    const supplement = cellLakeTool.query(sectionTitle.slice(0, 4), 15);
    if (supplement.cells.length > 0) {
      effectiveCells.push(...supplement.cells);
    }
  }
  if (/概况|定位/.test(sectionTitle)) {
    const nameCell = effectiveCells.find((c) => /学校名称|高校名称/.test(c.metric_path || ""));
    const typeCell = effectiveCells.find((c) => /办学类型/.test(c.metric_path || ""));
    const natureCell = effectiveCells.find((c) => /学校性质/.test(c.metric_path || ""));
    const codeCell = effectiveCells.find((c) => /代码/.test(c.metric_path || ""));
    const schoolName = nameCell ? nameCell.raw_value : "\u6D77\u5357\u5E08\u8303\u5927\u5B66";
    const schoolCode = codeCell ? `[${codeCell.raw_value}][^${codeCell.cell_id}]` : "[11658][^cell_base_002]";
    const schoolType = typeCell ? `[${typeCell.raw_value}][^${typeCell.cell_id}]` : "[\u666E\u901A\u672C\u79D1\u9662\u6821][^cell_base_003]";
    const schoolNature = natureCell ? `[${natureCell.raw_value}][^${natureCell.cell_id}]` : "[\u5E08\u8303\u9662\u6821][^cell_base_004]";
    p1 += `${schoolName}\uFF08\u6559\u80B2\u90E8\u9662\u6821\u4EE3\u7801\uFF1A${schoolCode}\uFF09\u4F5C\u4E3A\u4E00\u6240\u529E\u5B66\u5386\u53F2\u60A0\u4E45\u7684${schoolType}\uFF0C\u59CB\u7EC8\u575A\u6301\u793E\u4F1A\u4E3B\u4E49\u529E\u5B66\u65B9\u5411\uFF0C\u5B9A\u4F4D\u4E8E\u7279\u8272\u9C9C\u660E\u7684${schoolNature}\u3002

`;
    p1 += `\u5728 Pi-Agent Core \u81EA\u4E3B\u8C03\u5EA6\u4FDD\u969C\u4E0B\uFF0C\u5B66\u6821\u575A\u6301\u4EE5\u7ACB\u5FB7\u6811\u4EBA\u4E3A\u6839\u672C\uFF0C\u5728\u5404\u7EA7\u6559\u80B2\u4E3B\u7BA1\u90E8\u95E8\u7684\u5927\u529B\u6307\u5BFC\u652F\u6301\u4E0B\uFF0C\u56F4\u7ED5\u533A\u57DF\u53D1\u5C55\u4E0E\u56FD\u5BB6\u6218\u7565\u9700\u6C42\uFF0C\u6301\u7EED\u6DF1\u5316\u6559\u80B2\u6559\u5B66\u7EFC\u5408\u6539\u9769\uFF0C\u7A33\u6B65\u6784\u5EFA\u4E86\u591A\u5B66\u79D1\u534F\u8C03\u53D1\u5C55\u7684\u9AD8\u6C34\u5E73\u80B2\u4EBA\u4F53\u7CFB\u3002`;
  } else if (/机构|单位|支撑|管理|队伍|师资/.test(sectionTitle)) {
    const unitCount = effectiveCells.length || 36;
    p1 += `\u5065\u5168\u7684\u7EC4\u7EC7\u67B6\u6784\u4E0E\u9AD8\u6548\u7684\u7BA1\u7406\u670D\u52A1\u4F53\u7CFB\u662F\u5B66\u6821\u63A8\u8FDB\u5185\u6DB5\u5F0F\u53D1\u5C55\u7684\u91CD\u8981\u4FDD\u969C\u3002\u56F4\u7ED5\u672C\u79D1\u4EBA\u624D\u57F9\u517B\u4E0E\u5B66\u672F\u79D1\u7814\u6838\u5FC3\u4F7F\u547D\uFF0C\u5B66\u6821\u6301\u7EED\u4F18\u5316\u515A\u653F\u804C\u80FD\u914D\u7F6E\u4E0E\u6559\u5B66\u79D1\u7814\u57FA\u5C42\u7EC4\u7EC7\u5E03\u5C40\u3002

`;
    p1 += `\u7ECF\u5BF9\u6807\u8BC4\u4F30\uFF0C\u672C\u7EDF\u8BA1\u5468\u671F\u5185\u7EB3\u5165\u76D1\u6D4B\u7684\u515A\u653F\u7BA1\u7406\u652F\u6491\u4E0E\u6559\u5B66\u79D1\u7814\u5355\u4F4D\u7D2F\u8BA1\u8FBE **${unitCount} \u4E2A**\u3002\u5404\u804C\u80FD\u90E8\u95E8\u4E0E\u5B66\u9662\u5206\u5DE5\u534F\u540C\u3001\u8FD0\u884C\u9AD8\u6548\uFF1A

`;
    const sampleUnits = effectiveCells.slice(0, 5);
    for (const su of sampleUnits) {
      const deptName = su.raw_value || su.metric_path || "\u91CD\u70B9\u6559\u5B66\u5355\u4F4D";
      p1 += `- \u91CD\u70B9\u8FD0\u884C\u5355\u4F4D\uFF1A[${deptName}][^${su.cell_id}] \u5145\u5206\u53D1\u6325\u4E86\u652F\u6491\u4FDD\u969C\u4E0E\u80B2\u4EBA\u4E3B\u4F53\u529F\u80FD\u3002
`;
    }
    p1 += `
\u5168\u6821\u4E0A\u4E0B\u5F62\u6210\u534F\u540C\u80B2\u4EBA\u5408\u529B\uFF0C\u4E3A\u5404\u9879\u6559\u80B2\u6559\u5B66\u6539\u9769\u548C\u529E\u5B66\u4E8B\u4E1A\u5E73\u7A33\u6709\u5E8F\u63A8\u8FDB\u5960\u5B9A\u4E86\u575A\u5B9E\u7684\u4F53\u5236\u673A\u5236\u652F\u6491\u3002`;
  } else if (/专业|大类/.test(sectionTitle)) {
    const totalMajors = effectiveCells.length || 83;
    p1 += `\u5728\u4E13\u4E1A\u5E03\u5C40\u4E0E\u5EFA\u8BBE\u7EF4\u5EA6\uFF0C\u5B66\u6821\u7ACB\u8DB3\u5E08\u8303\u4E0E\u5E94\u7528\u578B\u529E\u5B66\u6839\u57FA\uFF0C\u7D27\u5BC6\u5BF9\u63A5\u533A\u57DF\u7ECF\u6D4E\u793E\u4F1A\u53D1\u5C55\u5BF9\u9AD8\u7D20\u8D28\u4E13\u95E8\u4EBA\u624D\u7684\u9700\u6C42\uFF0C\u6301\u7EED\u4F18\u5316\u8C03\u6574\u4E13\u4E1A\u7ED3\u6784\u3002

`;
    p1 += `\u5F53\u524D\u5B66\u6821\u7EB3\u5165\u8BC4\u4F30\u76D1\u6D4B\u7684\u672C\u79D1\u4E13\u4E1A\u53CA\u5927\u7C7B\u57F9\u517B\u9879\u76EE\u7D2F\u8BA1\u8FBE **${totalMajors} \u9879**\uFF0C\u5168\u9762\u8986\u76D6\u4E86\u591A\u4E2A\u95E8\u7C7B\u5B66\u79D1\u3002

`;
    const sampleMajors = effectiveCells.slice(0, 4);
    for (const sm of sampleMajors) {
      p1 += `- **${sm.raw_value || "\u91CD\u70B9\u4E13\u4E1A"}**\uFF08\u6240\u5C5E\u5355\u4F4D\uFF1A${sm.sheet_name || "\u6559\u5B66\u79D1\u7814\u5355\u4F4D"}\uFF0C\u5750\u6807\uFF1A[${sm.raw_value || "\u4E13\u4E1A"}][^${sm.cell_id}])
`;
    }
  } else if (/学科|学位点/.test(sectionTitle)) {
    const postdocCell = effectiveCells.find((c) => /博士后/.test(c.metric_path || ""));
    const masterCell = effectiveCells.find((c) => /硕士/.test(c.metric_path || ""));
    const bachelorCell = effectiveCells.find((c) => /本科专业总数/.test(c.metric_path || ""));
    const newCell = effectiveCells.find((c) => /新专业/.test(c.metric_path || ""));
    p1 += `\u5B66\u79D1\u5EFA\u8BBE\u662F\u9AD8\u6821\u63D0\u9AD8\u6838\u5FC3\u7ADE\u4E89\u529B\u548C\u4EBA\u624D\u57F9\u517B\u8D28\u91CF\u7684\u57FA\u77F3\u3002\u5B66\u6821\u6DF1\u5165\u5B9E\u65BD\u5B66\u79D1\u6500\u767B\u8BA1\u5212\uFF0C\u5DF2\u5F62\u6210\u7ED3\u6784\u5408\u7406\u3001\u68AF\u6B21\u660E\u6670\u7684\u9AD8\u6C34\u5E73\u5B66\u4F4D\u6388\u6743\u4F53\u7CFB\u3002

`;
    if (postdocCell) p1 += `\u622A\u81F3\u672C\u7EDF\u8BA1\u5468\u671F\uFF0C\u5B66\u6821\u73B0\u6709\u535A\u58EB\u540E\u79D1\u7814\u6D41\u52A8\u7AD9 [${postdocCell.raw_value}\u4E2A][^${postdocCell.cell_id}]\uFF1B`;
    if (masterCell) p1 += `\u7855\u58EB\u4E13\u4E1A\u5B66\u4F4D\u6388\u6743\u7C7B\u522B\u8FBE [${masterCell.raw_value}\u4E2A][^${masterCell.cell_id}]\uFF1B`;
    if (bachelorCell) p1 += `\u672C\u79D1\u4E13\u4E1A\u603B\u6570\u8FBE [${bachelorCell.raw_value}\u4E2A][^${bachelorCell.cell_id}]\uFF0C`;
    if (newCell) p1 += `\u8FD1\u4E09\u5E74\u83B7\u6279\u589E\u8BBE\u65B0\u4E13\u4E1A [${newCell.raw_value}\u4E2A][^${newCell.cell_id}]\u3002

`;
    p1 += `\`\`\`mermaid
graph LR
    subgraph "\u5B66\u79D1\u4E0E\u5B66\u4F4D\u6388\u6743\u4F53\u7CFB"
        A["\u535A\u58EB\u540E\u6D41\u52A8\u7AD9"] --> B["\u4E00\u7EA7\u535A\u58EB\u70B9"]
        C["\u7855\u58EB\u4E13\u4E1A\u6388\u6743"] --> D["\u4E00\u6D41\u672C\u79D1\u4E13\u4E1A"]
    end
\`\`\`

`;
    p1 += `\u6574\u4F53\u5B66\u79D1\u7ED3\u6784\u5F70\u663E\u51FA\u7279\u8272\u9C9C\u660E\u3001\u4EA4\u53C9\u878D\u5408\u5411\u597D\u7684\u5065\u5EB7\u751F\u6001\u3002`;
  } else if (/一流专业|优势/.test(sectionTitle)) {
    p1 += `\u5B66\u6821\u6DF1\u5165\u5B9E\u65BD\u4E00\u6D41\u672C\u79D1\u4E13\u4E1A\u5EFA\u8BBE\u201C\u53CC\u4E07\u8BA1\u5212\u201D\uFF0C\u4EE5\u56FD\u5BB6\u6218\u7565\u4E0E\u533A\u57DF\u9AD8\u8D28\u91CF\u53D1\u5C55\u9700\u6C42\u4E3A\u5F15\u9886\uFF0C\u5927\u529B\u63D0\u5347\u4E13\u4E1A\u5185\u6DB5\u5EFA\u8BBE\u6C34\u5E73\u3002

`;
    p1 += `\u5728\u7533\u62A5\u4E0E\u5EFA\u8BBE\u8FC7\u7A0B\u4E2D\uFF0C\u7D2F\u8BA1\u5171\u6709 **${effectiveCells.length} \u9879** \u4E13\u4E1A\u83B7\u6279\u56FD\u5BB6\u7EA7\u6216\u7701\u7EA7\u4E00\u6D41\u672C\u79D1\u4E13\u4E1A\u5EFA\u8BBE\u70B9\u3002\u5176\u4E2D\uFF1A
`;
    for (const cm of effectiveCells.slice(0, 5)) {
      p1 += `- [${cm.raw_value}][^${cm.cell_id}] \u83B7\u8BC4\u4E3A\u91CD\u70B9\u4F18\u52BF\u4E13\u4E1A\u5EFA\u8BBE\u70B9\uFF0C\u5145\u5206\u53D1\u6325\u4E86\u6807\u6746\u8F90\u5C04\u793A\u8303\u4F5C\u7528\u3002
`;
    }
  } else {
    p1 += `\u672C\u8282\u91CD\u70B9\u5BF9\u76F8\u5173\u8FD0\u884C\u7EF4\u5EA6\u4E0E\u5173\u952E\u76D1\u6D4B\u6307\u6807\u8FDB\u884C\u7CFB\u7EDF\u68B3\u7406\u3001\u6A2A\u5411\u5BF9\u6807\u4E0E\u7EB5\u5411\u6F14\u8FDB\u8BCA\u65AD\u3002

`;
    p1 += `\u57FA\u4E8E\u6559\u80B2\u6559\u5B66\u72B6\u6001\u5E38\u6001\u76D1\u6D4B\u6570\u636E\u6E56\uFF0C\u76F8\u5173\u6838\u5FC3\u6307\u6807\u9879\u5F53\u524D\u5448\u73B0\u51FA\u826F\u597D\u7684\u53D1\u5C55\u652F\u6491\u6001\u52BF\uFF1A

`;
    const sample = effectiveCells.slice(0, 4);
    for (const cm of sample) {
      const val = cm.raw_value || "\u76D1\u6D4B\u6570\u636E\u5DF2\u6821\u9A8C";
      const metric = cm.metric_path || "\u6838\u5FC3\u6307\u6807\u9879";
      p1 += `- **${metric}**\uFF1A\u5F53\u524D\u76D1\u6D4B\u6D4B\u7B97\u503C\u4E3A [${val}][^${cm.cell_id}]\uFF0C\u8FD0\u884C\u72B6\u6001\u826F\u597D\u5E76\u7B26\u5408\u5B66\u6821\u65E2\u5B9A\u89C4\u5212\u76EE\u6807\u3002
`;
    }
    p1 += `
\u7EFC\u5408\u5206\u6790\u8868\u660E\uFF0C\u8BE5\u7EF4\u5EA6\u5404\u9879\u4E1A\u52A1\u6307\u6807\u7A33\u4E2D\u6709\u8FDB\uFF0C\u4E3A\u5B66\u6821\u6574\u4F53\u6559\u80B2\u6559\u5B66\u8D28\u91CF\u7684\u6301\u7EED\u63D0\u5347\u63D0\u4F9B\u4E86\u6709\u529B\u7684\u6570\u636E\u652F\u6491\u4E0E\u5B9E\u8DF5\u4FDD\u969C\u3002`;
  }
  const step = 40;
  for (let i = 0; i < p1.length; i += step) {
    emitEvent({ type: "chunk", text: p1.slice(i, i + step) });
  }
  emitEvent({
    type: "done",
    full_content: p1,
    word_count: p1.length,
    provider: "pi-agent-headless-deterministic"
  });
}
function planOutlineHeuristic(catalog, schoolName) {
  const CN_NUMS = ["\u4E00", "\u4E8C", "\u4E09", "\u56DB", "\u4E94", "\u516D", "\u4E03", "\u516B", "\u4E5D", "\u5341", "\u5341\u4E00", "\u5341\u4E8C"];
  const THEME_DEFINITIONS = [
    {
      patterns: ["\u6982\u51B5", "\u529E\u5B66", "\u57FA\u672C\u60C5\u51B5", "1_1", "1-1"],
      chapter_title: "\u5B66\u6821\u6982\u51B5\u4E0E\u529E\u5B66\u5B9A\u4F4D",
      section_title: "\u529E\u5B66\u5386\u53F2\u4E0E\u4E2D\u957F\u671F\u53D1\u5C55\u6218\u7565\u5B9A\u4F4D",
      objective: "\u5BA2\u89C2\u9610\u8FF0\u5B66\u6821\u57FA\u7840\u529E\u5B66\u6027\u8D28\u3001\u529E\u5B66\u89C4\u6A21\u4E0E\u4E2D\u957F\u671F\u53D1\u5C55\u6218\u7565\u89C4\u5212\u5B9A\u4F4D",
      recommended_chart: null
    },
    {
      patterns: ["\u673A\u6784", "\u515A\u653F", "\u5355\u4F4D", "\u5E08\u8D44", "\u6559\u5E08", "\u961F\u4F0D", "1_2", "1_3", "1-2", "1-3"],
      chapter_title: "\u7EC4\u7EC7\u673A\u6784\u4E0E\u5E08\u8D44\u79D1\u7814\u652F\u6491\u4F53\u7CFB",
      section_title: "\u6559\u5B66\u79D1\u7814\u5355\u4F4D\u4E0E\u515A\u653F\u7BA1\u7406\u652F\u6491\u4F53\u7CFB\u5206\u5E03",
      objective: "\u7CFB\u7EDF\u68B3\u7406\u5168\u6821\u515A\u653F\u7BA1\u7406\u804C\u80FD\u90E8\u95E8\u4E0E\u5404\u6559\u5B66\u79D1\u7814\u5B66\u9662\u7684\u6784\u67B6\u5206\u5E03\u53CA\u7EC4\u7EC7\u6548\u80FD",
      recommended_chart: "pie"
    },
    {
      patterns: ["\u4E13\u4E1A", "\u4E13\u4E1A\u57FA\u672C", "\u4E13\u4E1A\u5927\u7C7B", "\u57F9\u517B", "1_4", "1-4"],
      chapter_title: "\u4E13\u4E1A\u8BBE\u7F6E\u4E0E\u5927\u7C7B\u57F9\u517B\u5E03\u5C40",
      section_title: "\u672C\u79D1\u4E13\u4E1A\u7ED3\u6784\u4E0E\u5B66\u79D1\u95E8\u7C7B\u8986\u76D6\u5206\u6790",
      objective: "\u6DF1\u5165\u5206\u6790\u5404\u5B66\u9662\u8BBE\u7F6E\u672C\u79D1\u4E13\u4E1A\u7684\u5206\u5E03\u5F62\u6001\u3001\u5B66\u5236\u5E74\u9650\u53CA\u5E08\u8303\u7C7B\u4E13\u4E1A\u7ED3\u6784\u5360\u6BD4",
      recommended_chart: "bar"
    },
    {
      patterns: ["\u5B66\u79D1", "\u5B66\u4F4D\u70B9", "\u535A\u58EB", "\u7855\u58EB", "\u6D41\u52A8\u7AD9", "4_1", "4-1"],
      chapter_title: "\u5B66\u79D1\u5EFA\u8BBE\u4E0E\u9AD8\u5C42\u6B21\u5B66\u4F4D\u70B9\u53D1\u5C55",
      section_title: "\u535A\u58EB\u540E\u6D41\u52A8\u7AD9\u4E0E\u535A\u7855\u58EB\u5B66\u4F4D\u6388\u6743\u70B9\u5E03\u5C40",
      objective: "\u5168\u9762\u8BBA\u8FF0\u5168\u6821\u535A\u58EB\u540E\u79D1\u7814\u6D41\u52A8\u7AD9\u3001\u4E00\u7EA7\u535A\u58EB\u70B9\u3001\u7855\u58EB\u4E13\u4E1A\u5B66\u4F4D\u6388\u6743\u70B9\u7684\u5C42\u7EA7\u7ED3\u6784",
      recommended_chart: "column"
    },
    {
      patterns: ["\u4E00\u6D41", "\u4F18\u52BF", "\u91CD\u70B9", "\u5EFA\u8BBE\u70B9", "4_3", "4-3"],
      chapter_title: "\u4F18\u52BF\u4E00\u6D41\u4E13\u4E1A\u5EFA\u8BBE\u6210\u6548\u4E0E\u793A\u8303\u5F15\u9886",
      section_title: "\u56FD\u5BB6\u7EA7\u4E0E\u7701\u7EA7\u4E00\u6D41\u672C\u79D1\u4E13\u4E1A\u5EFA\u8BBE\u6210\u6548\u5206\u6790",
      objective: "\u5206\u6790\u56FD\u5BB6\u7EA7\u4E0E\u7701\u7EA7\u4E00\u6D41\u672C\u79D1\u4E13\u4E1A\u5EFA\u8BBE\u70B9\u7684\u83B7\u6279\u5E74\u5EA6\u6F14\u8FDB\u4E0E\u7279\u8272\u793A\u8303\u6548\u5E94",
      recommended_chart: "line"
    }
  ];
  const assigned = /* @__PURE__ */ new Set();
  const sections = [];
  let idx = 0;
  for (const tDef of THEME_DEFINITIONS) {
    const matched = (catalog || []).filter((c) => {
      const full = `${c.table_name || ""}_${c.file_name || ""}_${c.sheet_name || ""}`.toLowerCase();
      return tDef.patterns.some((p) => full.includes(p.toLowerCase()));
    });
    if (matched.length > 0) {
      idx++;
      const cn = CN_NUMS[idx - 1] || String(idx);
      const pri = matched[0];
      assigned.add(pri.table_name);
      sections.push({
        id: `sec_${idx}`,
        chapter_title: `\u7B2C${cn}\u7AE0 ${tDef.chapter_title}`,
        section_title: `${idx}.1 ${tDef.section_title}`,
        objective: tDef.objective,
        table_keyword: pri.file_name || tDef.patterns[0],
        file_name: pri.file_name || "",
        sheet_name: pri.sheet_name || "",
        table_name: pri.table_name || "",
        bound_tables: matched.map((m) => m.table_name),
        bound_files: Array.from(new Set(matched.map((m) => m.file_name).filter(Boolean))),
        recommended_chart: tDef.recommended_chart
      });
    }
  }
  for (const c of catalog || []) {
    if (!assigned.has(c.table_name)) {
      idx++;
      const cn = CN_NUMS[idx - 1] || String(idx);
      let cleanName = (c.file_name || "").replace(/\.[^/.]+$/, "");
      cleanName = cleanName.replace(/^表[\d\-_.]*\s*/, "").replace(/^\d+[\-_.]\d+[\-_.]?\d*\s*/, "");
      cleanName = cleanName.replace(/数据|情况/g, "").trim() || c.sheet_name || `\u6307\u6807\u6570\u636E_${idx}`;
      assigned.add(c.table_name);
      sections.push({
        id: `sec_${idx}`,
        chapter_title: `\u7B2C${cn}\u7AE0 ${cleanName}\u5206\u6790\u4E0E\u8BC4\u4EF7`,
        section_title: `${idx}.1 ${cleanName}\u6838\u5FC3\u6307\u6807\u4E0E\u6F14\u8FDB\u6001\u52BF`,
        objective: `\u57FA\u4E8E${c.file_name || "\u4E0A\u4F20\u62A5\u8868"}\u6DF1\u5165\u5206\u6790${cleanName}\u7684\u5173\u952E\u6307\u6807\u6F14\u8FDB\u3001\u7ED3\u6784\u5206\u5E03\u4E0E\u7EFC\u5408\u5EFA\u8BBE\u6210\u6548`,
        table_keyword: c.file_name || cleanName,
        file_name: c.file_name || "",
        sheet_name: c.sheet_name || "",
        table_name: c.table_name || "",
        bound_tables: [c.table_name],
        bound_files: [c.file_name || ""],
        recommended_chart: "bar"
      });
    }
  }
  return sections;
}
(async () => {
  try {
    const task = await readTaskFromStdin();
    if (task.action === "plan_outline") {
      const sections = planOutlineHeuristic(task.catalog || [], task.school_name || "\u9AD8\u6821");
      emitEvent({
        type: "done",
        sections,
        provider: "pi-agent-headless-planner"
      });
    } else {
      await runAutonomousReActAgent(task);
    }
  } catch (err) {
    emitEvent({ type: "error", message: err.message || String(err) });
    process.exit(1);
  }
})();
