export type PageId = 'overview' | 'data' | 'generation' | 'reader' | 'settings'

export interface AuthUser {
  id: number
  username: string
  display_name: string
}

export interface AuthSubmission {
  mode: 'login' | 'register'
  username: string
  displayName: string
  password: string
}
export type SectionStatus =
  | 'pending'
  | 'retrieving'
  | 'retrieved'
  | 'writing'
  | 'auditing'
  | 'refining'
  | 'audited'
  | 'warning'
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'


export interface DatasetInfo {
  id: string
  dataset_id?: string
  name: string
  academic_year: string
  kind: 'legacy' | 'real' | 'demo'
  is_default: number | boolean
  current_revision: number
  status: string
  cell_count: number
  table_count: number
  report_count: number
  latest_report_id: string
  latest_report_status: string
  detected_school_name?: string
  created_at?: number
  updated_at?: number
}

export interface SchoolProfile {
  school_name: string
  school_code: string
}

export interface SheetInfo {
  table_name: string
  file_name: string
  sheet_name: string
  row_count: number
  columns?: string[]
  headers?: string[]
  cells_count?: number
}

export interface Citation {
  cell_id: string
  cited_text: string
  raw_value: string
  file_name: string
  sheet_name: string
  cell_ref: string
  metric_path: string
  is_verified: boolean
  status: string
}

export interface CitationAudit {
  total_citations: number
  verified_count: number
  mismatch_count: number
  pass_rate: number
  is_approved: boolean
  citations: Citation[]
}

export interface JudgeResult {
  logic_score?: number
  is_clean?: boolean
  approved?: boolean
  rejection_reason?: string
  provider?: string
}

export interface AuditBundle {
  audit_res: CitationAudit
  jev_res: JudgeResult
  passed: boolean
}

export interface OutlineAudit {
  structure_score?: number
  is_approved?: boolean
  critique?: string
  provider?: string
}

export interface ReportSection {
  id: string
  chapter_title: string
  section_title: string
  objective: string
  file_name?: string
  sheet_name?: string
  table_name?: string
  bound_files?: string[]
  status: SectionStatus
  content: string
  audit: AuditBundle | null
  points_count?: number
}

export interface GeneratedSection {
  id: string
  title: string
  content: string
  audit: CitationAudit
  jev: JudgeResult
  passed: boolean
}

export interface ExportFiles {
  docx?: string
  xlsx?: string
  docx_url?: string
  xlsx_url?: string
}

export interface PipelineSnapshot {
  is_running?: boolean
  data_changed?: boolean
  outline_audit?: OutlineAudit
  school_name?: string
  current_stage: number
  sections_plan: Partial<ReportSection>[]
  generated_sections: GeneratedSection[]
  export_files: ExportFiles
  dataset_id?: string
  dataset_name?: string
  dataset_kind?: string
  dataset_academic_year?: string
  current_revision?: number
  report_version_id?: string
  report_version_status?: string
  revision_no?: number
  report_created_at?: number | null
  report_completed_at?: number | null
}

export interface CellInfo {
  cell_id: string
  file_name: string
  sheet_name: string
  cell_ref: string
  metric_path: string
  raw_value: string
}

export interface ExecutionLog {
  time: string
  message: string
  level: 'info' | 'success' | 'warning' | 'error'
}

export interface ModelConfig {
  clearApiKey: boolean
  apiKey: string
  baseUrl: string
  model: string
  agentMode: 'pi_agent' | 'python_native'
}
