import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { ReportSection, TagType } from '../types'

function escapeHtml(text: string) {
  return text.replace(
    /[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!,
  )
}

// Keep readable values and source links, without exposing internal citation identifiers.
export function renderReportMarkdown(markdown: string, displayedHeadings: string[] = []) {
  const seenImages = new Set<string>()
  const normalizeHeading = (text: string) => text.replace(/\s+/g, '').replace(/[。:：]$/, '')
  const headings = new Set(displayedHeadings.filter(Boolean).map(normalizeHeading))
  let text = markdown
    .replace(/^#{1,3}\s+(.+)$/gm, (match, heading: string) =>
      headings.has(normalizeHeading(heading)) ? '' : match,
    )
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, _alt, url: string) => {
      if (seenImages.has(url.trim())) return ''
      seenImages.add(url.trim())
      return match
    })
  text = text
    .replace(/^\s*\[\s*\^\s*cell_[^\]\r\n]*\]\s*[:：].*$/gim, '')
    .replace(
      /\[((?!\s*\^\s*cell_)[^\]\r\n]+)\]\s*\[\s*\^\s*(cell_[a-zA-Z0-9_]+)\s*\]/gi,
      (_match, value: string, id: string) =>
        `<span class="lake-citation" data-cell-id="${id}" tabindex="0" role="button" aria-label="查看数据来源">${escapeHtml(value)}</span>`,
    )
    .replace(/\[\s*\^\s*cell_[^\]\r\n]*\]/gi, '')
    .replace(/\[\s*\^\s*cell_[^\]\r\n]*$/gi, '')
  return DOMPurify.sanitize(marked.parse(text, { async: false }), {
    ADD_ATTR: ['data-cell-id', 'tabindex', 'role', 'aria-label'],
  })
}

export function qualityState(section: ReportSection): 'passed' | 'warning' | 'pending' {
  if (!section.audit) return 'pending'
  return section.audit.passed && section.audit.audit_res.total_citations > 0 ? 'passed' : 'warning'
}

export function sectionStatus(section: ReportSection): { label: string; type: TagType } {
  if (section.audit) {
    return qualityState(section) === 'passed'
      ? { label: '质检通过', type: 'success' }
      : { label: '核验异常', type: 'warning' }
  }
  const labels: Record<string, string> = {
    pending: '待生成',
    retrieving: '检索数据',
    retrieved: '数据就绪',
    writing: '正在撰写',
    auditing: '正在质检',
    refining: '修订中',
  }
  return {
    label: labels[section.status] || '待核验',
    type: section.status === 'pending' ? 'info' : 'primary',
  }
}

export function citationSummary(section: ReportSection) {
  const audit = section.audit?.audit_res
  return audit?.total_citations
    ? `${audit.verified_count} / ${audit.total_citations} 条`
    : '未提取引用'
}

export function judgeProvider(provider?: string) {
  if (!provider) return '尚未评审'
  if (
    provider === 'jev-deterministic-rules' ||
    provider.includes('local') ||
    provider.includes('deterministic')
  )
    return '本地规则'
  if (provider === 'deepseek-judge') return 'DeepSeek 评审'
  return provider
}

export function sectionAnchor(id: string) {
  return `report-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`
}
