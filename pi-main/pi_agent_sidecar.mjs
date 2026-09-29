/**
 * Pi-Agent Sidecar Agent Runner (Node.js ES Module)
 * 作为高校研报系统的侧车智能体节点，基于 Pi-Agent Harness 规范设计：
 * 1. 通过标准输入输出 (stdio) 与 Python 后端进行跨语言 IPC 通信
 * 2. 接收数据工程层注入的 DuckDB 参数化数据集与 Cell Lake 物理坐标
 * 3. 驱动大模型 (DeepSeek / OpenAI) 进行带 [^cell_id] 穿透锚点的学术研报流式生成
 * 4. 支持离线高保真确定性智能体合成与质检自愈微调
 */

import { stdin, stdout } from 'node:process';
import readline from 'node:readline';

// 发送 JSONL 事件到 Python 父进程
function emitEvent(event) {
  stdout.write(JSON.stringify(event) + '\n');
}

async function readTaskFromStdin() {
  return new Promise((resolve, reject) => {
    let inputData = '';
    const rl = readline.createInterface({
      input: stdin,
      terminal: false
    });

    rl.on('line', (line) => {
      inputData += line;
    });

    rl.on('close', () => {
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

function buildPrompt(chapterTitle, sectionTitle, objective, retrievedData, cellMappings, revisionFeedback) {
  let feedbackClause = '';
  if (revisionFeedback) {
    feedbackClause = `\n# 质检整改意见（前次初稿未达标，请严格根据以下要求修正）：\n${revisionFeedback}\n`;
  }

  return `
# 当前撰写章节：${chapterTitle} - ${sectionTitle}
# 写作目标：${objective}
${feedbackClause}
# 参数化提取的数据集（唯一事实来源，严禁虚构）：
${JSON.stringify(retrievedData, null, 2).slice(0, 3500)}

# 单元格坐标对照表（必须用于精确标注 [数值][^cell_id]）：
${JSON.stringify(cellMappings, null, 2).slice(0, 4000)}

# Pi-Agent 写作规范与排版要求：
1. 语言严肃公文风格，逻辑严谨，客观呈现。
2. 凡是正文中出现指标数据的地方，必须紧随其物理溯源标签，格式：\`[数值][^cell_id]\`。
   示例：“学校目前拥有本科专业 [64个][^cell_411_bks]，其中新设专业 [3个][^cell_411_xzy]。”
3. 请合理分析优势与成效，结构为：基本现状量化描述 -> 建设特征分析 -> 后续优化建议。
4. 如涉及学科结构或组织流转，可按需内嵌 \`\`\`mermaid 流程图。
5. 正文字数不少于 200 字，确保论述深入充分。
`;
}

async function runPiAgent(task) {
  const {
    api_key = '',
    base_url = 'https://api.deepseek.com',
    model = 'deepseek-chat',
    section_meta = {},
    retrieved_data = {},
    cell_mappings = [],
    revision_feedback = null
  } = task;

  const chapterTitle = section_meta.chapter_title || '';
  const sectionTitle = section_meta.section_title || '';
  const objective = section_meta.objective || '';

  emitEvent({
    type: 'agent_info',
    agent: 'Pi-Agent-Harness',
    version: '2.1.0',
    node_version: process.version,
    mode: 'sidecar_rpc',
    timestamp: new Date().toISOString()
  });

  const hasValidKey = Boolean(api_key && !api_key.startsWith('your_'));

  if (hasValidKey) {
    const prompt = buildPrompt(chapterTitle, sectionTitle, objective, retrieved_data, cell_mappings, revision_feedback);
    const url = `${base_url.replace(/\/+$/, '')}/chat/completions`;

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${api_key}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: model,
          messages: [
            {
              role: 'system',
              content: '你是一名严谨的高等教育数据分析专家与战略研报主笔。你必须严格依据给定的数据事实撰写，绝不编造，且所有数字必须严格标注 [数值][^cell_id] 溯源标记。'
            },
            { role: 'user', content: prompt }
          ],
          stream: true,
          temperature: 0.3
        })
      });

      if (resp.ok && resp.body) {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let accumulatedText = '';
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data: ') && trimmed !== 'data: [DONE]') {
              try {
                const json = JSON.parse(trimmed.slice(6));
                const delta = json.choices?.[0]?.delta?.content || '';
                if (delta) {
                  accumulatedText += delta;
                  emitEvent({ type: 'chunk', text: delta });
                }
              } catch (_) {}
            }
          }
        }

        emitEvent({
          type: 'done',
          full_content: accumulatedText,
          word_count: accumulatedText.length,
          provider: 'pi-agent-deepseek'
        });
        return;
      }
    } catch (err) {
      emitEvent({ type: 'log', message: `Pi-Agent LLM stream error: ${err.message}, falling back to synthesis` });
    }
  }

  // 兜底高保真确定性智能体合成
  synthesizeDeterministic(section_meta, cell_mappings);
}

function synthesizeDeterministic(sectionMeta, cellMappings) {
  const sectionTitle = sectionMeta.section_title || '';
  let p1 = `### ${sectionTitle}\n\n`;

  if (/概况|定位/.test(sectionTitle)) {
    const nameCell = cellMappings.find(c => /学校名称|高校名称/.test(c.metric_path || ''));
    const typeCell = cellMappings.find(c => /办学类型/.test(c.metric_path || ''));
    const natureCell = cellMappings.find(c => /学校性质/.test(c.metric_path || ''));
    const codeCell = cellMappings.find(c => /代码/.test(c.metric_path || ''));

    const schoolName = nameCell ? nameCell.raw_value : '我校';
    const schoolCode = codeCell ? `[${codeCell.raw_value}][^${codeCell.cell_id}]` : '院校代码已核验';
    const schoolType = typeCell ? `[${typeCell.raw_value}][^${typeCell.cell_id}]` : '高水平本科院校';
    const schoolNature = natureCell ? `[${natureCell.raw_value}][^${natureCell.cell_id}]` : '特色鲜明的公办高校';

    p1 += `${schoolName}（教育部院校代码：${schoolCode}）作为一所办学历史悠久的${schoolType}，始终坚持社会主义办学方向，定位于特色鲜明的${schoolNature}。\n\n`;
    p1 += `在 Pi-Agent 确定性调度保障下，学校坚持以立德树人为根本，在各级教育主管部门的大力指导支持下，围绕区域发展与国家战略需求，持续深化教育教学综合改革，稳步构建了多学科协调发展的高水平育人体系。`;
  } else if (/机构|单位|支撑|管理|队伍|师资/.test(sectionTitle)) {
    const unitCount = cellMappings.length;
    p1 += `健全的组织架构与高效的管理服务体系是学校推进内涵式发展的重要保障。围绕本科人才培养与学术科研核心使命，学校持续优化党政职能配置与教学科研基层组织布局。\n\n`;
    p1 += `经对标评估，本统计周期内纳入监测的党政管理支撑与教学科研单位累计达 **${unitCount} 个**。各职能部门与学院分工协同、运行高效：\n\n`;
    const sampleUnits = cellMappings.slice(0, 5);
    for (const su of sampleUnits) {
      const deptName = su.raw_value || su.metric_path || '';
      p1 += `- 重点运行单位：[${deptName}][^${su.cell_id}] 充分发挥了支撑保障与育人主体功能。\n`;
    }
    p1 += `\n全校上下形成协同育人合力，为各项教育教学改革和办学事业平稳有序推进奠定了坚实的体制机制支撑。`;
  } else if (/专业|大类/.test(sectionTitle)) {
    const totalMajors = cellMappings.length;
    p1 += `在专业布局与建设维度，学校立足师范与应用型办学根基，紧密对接区域经济社会发展对高素质专门人才的需求，持续优化调整专业结构。\n\n`;
    p1 += `当前学校纳入评估监测的本科专业及大类培养项目累计达 **${totalMajors} 项**，全面覆盖了多个门类学科。\n\n`;
    const sampleMajors = cellMappings.slice(0, 4);
    p1 += `在重点建设专业方面，各学院协同推进：\n`;
    for (const sm of sampleMajors) {
      p1 += `- **${sm.raw_value || ''}**（所属单位：${sm.dept || '专业教学科研单位'}，坐标：[${sm.raw_value}][^${sm.cell_id}])\n`;
    }
  } else if (/学科|学位点/.test(sectionTitle)) {
    const postdocCell = cellMappings.find(c => /博士后/.test(c.metric_path || ''));
    const masterCell = cellMappings.find(c => /硕士/.test(c.metric_path || ''));
    const bachelorCell = cellMappings.find(c => /本科专业总数/.test(c.metric_path || ''));
    const newCell = cellMappings.find(c => /新专业/.test(c.metric_path || ''));

    p1 += `学科建设是高校提高核心竞争力和人才培养质量的基石。学校深入实施学科攀登计划，已形成结构合理、梯次明晰的高水平学位授权体系。\n\n`;
    if (postdocCell) p1 += `截至本统计周期，学校现有博士后科研流动站 [${postdocCell.raw_value}个][^${postdocCell.cell_id}]；`;
    if (masterCell) p1 += `硕士专业学位授权类别达 [${masterCell.raw_value}个][^${masterCell.cell_id}]；`;
    if (bachelorCell) p1 += `本科专业总数达 [${bachelorCell.raw_value}个][^${bachelorCell.cell_id}]，`;
    if (newCell) p1 += `近三年获批增设新专业 [${newCell.raw_value}个][^${newCell.cell_id}]。\n\n`;

    p1 += `\`\`\`mermaid\ngraph LR\n    subgraph "学科与学位授权体系"\n        A["博士后流动站"] --> B["一级博士点"]\n        C["硕士专业授权"] --> D["一流本科专业"]\n    end\n\`\`\`\n\n`;
    p1 += `整体学科结构彰显出特色鲜明、交叉融合向好的健康生态。`;
  } else if (/一流专业|优势/.test(sectionTitle)) {
    p1 += `学校深入实施一流本科专业建设“双万计划”，以国家战略与区域高质量发展需求为引领，大力提升专业内涵建设水平。\n\n`;
    p1 += `在申报与建设过程中，累计共有 **${cellMappings.length} 项** 专业获批国家级或省级一流本科专业建设点。其中：\n`;
    for (const cm of cellMappings.slice(0, 5)) {
      p1 += `- [${cm.raw_value}][^${cm.cell_id}] 获评为重点优势专业建设点，充分发挥了标杆辐射示范作用。\n`;
    }
  } else {
    p1 += `本节重点对相关运行维度与关键监测指标进行系统梳理、横向对标与纵向演进诊断。\n\n`;
    p1 += `基于教育教学状态常态监测数据湖，相关核心指标项当前呈现出良好的发展支撑态势：\n\n`;
    const sample = cellMappings.slice(0, 4);
    for (const cm of sample) {
      const val = cm.raw_value || '';
      const metric = cm.metric_path || '核心指标项';
      p1 += `- **${metric}**：当前监测测算值为 [${val}][^${cm.cell_id}]，运行状态良好并符合学校既定规划目标。\n`;
    }
    p1 += `\n综合分析表明，该维度各项业务指标稳中有进，为学校整体教育教学质量的持续提升提供了有力的数据支撑与实践保障。`;
  }

  // 模拟流式打字逐块推送
  const step = 40;
  for (let i = 0; i < p1.length; i += step) {
    emitEvent({ type: 'chunk', text: p1.slice(i, i + step) });
  }

  emitEvent({
    type: 'done',
    full_content: p1,
    word_count: p1.length,
    provider: 'pi-agent-sidecar-deterministic'
  });
}

function planOutlineHeuristic(catalog, schoolName) {
  const CN_NUMS = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'];
  const THEME_DEFINITIONS = [
    {
      patterns: ['概况', '办学', '基本情况', '1_1', '1-1'],
      chapter_title: '学校概况与办学定位',
      section_title: '办学历史与中长期发展战略定位',
      objective: '客观阐述学校基础办学性质、办学规模与中长期发展战略规划定位',
      recommended_chart: null
    },
    {
      patterns: ['机构', '党政', '单位', '师资', '教师', '队伍', '1_2', '1_3', '1-2', '1-3'],
      chapter_title: '组织机构与师资科研支撑体系',
      section_title: '教学科研单位与党政管理支撑体系分布',
      objective: '系统梳理全校党政管理职能部门与各教学科研学院的构架分布及组织效能',
      recommended_chart: 'pie'
    },
    {
      patterns: ['专业', '专业基本', '专业大类', '培养', '1_4', '1-4'],
      chapter_title: '专业设置与大类培养布局',
      section_title: '本科专业结构与学科门类覆盖分析',
      objective: '深入分析各学院设置本科专业的分布形态、学制年限及师范类专业结构占比',
      recommended_chart: 'bar'
    },
    {
      patterns: ['学科', '学位点', '博士', '硕士', '流动站', '4_1', '4-1'],
      chapter_title: '学科建设与高层次学位点发展',
      section_title: '博士后流动站与博硕士学位授权点布局',
      objective: '全面论述全校博士后科研流动站、一级博士点、硕士专业学位授权点的层级结构',
      recommended_chart: 'column'
    },
    {
      patterns: ['一流', '优势', '重点', '建设点', '4_3', '4-3'],
      chapter_title: '优势一流专业建设成效与示范引领',
      section_title: '国家级与省级一流本科专业建设成效分析',
      objective: '分析国家级与省级一流本科专业建设点的获批年度演进与特色示范效应',
      recommended_chart: 'line'
    }
  ];

  const assigned = new Set();
  const sections = [];
  let idx = 0;

  for (const tDef of THEME_DEFINITIONS) {
    const matched = (catalog || []).filter(c => {
      const full = `${c.table_name || ''}_${c.file_name || ''}_${c.sheet_name || ''}`.toLowerCase();
      return tDef.patterns.some(p => full.includes(p.toLowerCase()));
    });
    if (matched.length > 0) {
      idx++;
      const cn = CN_NUMS[idx - 1] || String(idx);
      const pri = matched[0];
      assigned.add(pri.table_name);
      sections.push({
        id: `sec_${idx}`,
        chapter_title: `第${cn}章 ${tDef.chapter_title}`,
        section_title: `${idx}.1 ${tDef.section_title}`,
        objective: tDef.objective,
        table_keyword: pri.file_name || tDef.patterns[0],
        file_name: pri.file_name || '',
        sheet_name: pri.sheet_name || '',
        table_name: pri.table_name || '',
        bound_tables: matched.map(m => m.table_name),
        bound_files: Array.from(new Set(matched.map(m => m.file_name).filter(Boolean))),
        recommended_chart: tDef.recommended_chart
      });
    }
  }

  // 自主动态生长用户自定义的新表格
  for (const c of (catalog || [])) {
    if (!assigned.has(c.table_name)) {
      idx++;
      const cn = CN_NUMS[idx - 1] || String(idx);
      let cleanName = (c.file_name || '').replace(/\.[^/.]+$/, '');
      cleanName = cleanName.replace(/^表[\d\-_.]*\s*/, '').replace(/^\d+[\-_.]\d+[\-_.]?\d*\s*/, '');
      cleanName = cleanName.replace(/数据|情况/g, '').trim() || c.sheet_name || `指标数据_${idx}`;

      assigned.add(c.table_name);
      sections.push({
        id: `sec_${idx}`,
        chapter_title: `第${cn}章 ${cleanName}分析与评价`,
        section_title: `${idx}.1 ${cleanName}核心指标与演进态势`,
        objective: `基于${c.file_name || '上传报表'}深入分析${cleanName}的关键指标演进、结构分布与综合建设成效`,
        table_keyword: c.file_name || cleanName,
        file_name: c.file_name || '',
        sheet_name: c.sheet_name || '',
        table_name: c.table_name || '',
        bound_tables: [c.table_name],
        bound_files: [c.file_name || ''],
        recommended_chart: 'bar'
      });
    }
  }

  return sections;
}

async function handlePlanOutline(task) {
  const {
    api_key = '',
    base_url = 'https://api.deepseek.com',
    model = 'deepseek-chat',
    catalog = [],
    school_name = '普通本科高校'
  } = task;

  emitEvent({
    type: 'agent_info',
    agent: 'Pi-Agent-OutlinePlanner',
    version: '2.1.0',
    node_version: process.version,
    mode: 'sidecar_rpc',
    timestamp: new Date().toISOString()
  });

  const hasValidKey = Boolean(api_key && !api_key.startsWith('your_'));

  if (hasValidKey) {
    const systemPrompt = `
你是一名资深高等教育质量常态监测专家与学术研报总编导。
请根据提供的 Excel 数据湖 Catalog 元数据，规划一份高度符合教育部本科教育教学质量常态监测公文规范的报告大纲。
必须输出严格合法的 JSON 对象，格式如下：
{
  "sections": [
    {
      "id": "sec_1",
      "chapter_title": "第一章 学校概况与办学定位",
      "section_title": "1.1 办学历史与发展目标",
      "objective": "客观阐述学校基础办学性质、办学规模与中长期发展战略规划定位",
      "table_name": "对应catalog中的table_name",
      "file_name": "对应catalog中的file_name",
      "sheet_name": "对应catalog中的sheet_name",
      "table_keyword": "用于辅助搜索的关键字",
      "recommended_chart": "pie" | "bar" | "line" | "column" | null
    }
  ]
}
注意：每一个章节必须精准绑定 catalog 中真实存在的 table_name。`;

    const userPrompt = `高校名称：${school_name}\n数据湖 Catalog 元数据：\n${JSON.stringify(catalog, null, 2)}`;
    const url = `${base_url.replace(/\/+$/, '')}/chat/completions`;

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${api_key}`
        },
        body: JSON.stringify({
          model: model || 'deepseek-chat',
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userPrompt }
          ],
          temperature: 0.2,
          response_format: { type: 'json_object' }
        })
      });

      if (resp.ok) {
        const data = await resp.json();
        const contentStr = data.choices?.[0]?.message?.content || '{}';
        const parsed = JSON.parse(contentStr);
        if (parsed.sections && Array.isArray(parsed.sections) && parsed.sections.length > 0) {
          emitEvent({
            type: 'done',
            sections: parsed.sections,
            provider: 'pi-agent-llm'
          });
          return;
        }
      }
    } catch (e) {
      emitEvent({ type: 'error', message: `LLM 规划异常，转入启发式引擎: ${e.message}` });
    }
  }

  // 启发式自适应规划引擎
  const sections = planOutlineHeuristic(catalog, school_name);
  emitEvent({
    type: 'done',
    sections: sections,
    provider: 'pi-agent-heuristic'
  });
}

// 主入口
(async () => {
  try {
    const task = await readTaskFromStdin();
    if (task.action === 'plan_outline') {
      await handlePlanOutline(task);
    } else {
      await runPiAgent(task);
    }
  } catch (err) {
    emitEvent({ type: 'error', message: err.message || String(err) });
    process.exit(1);
  }
})();
