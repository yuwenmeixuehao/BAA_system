export type ReportScenario = 'market_performance' | 'inventory_anomaly' | 'general'
export type ConclusionStatus = 'confirmed' | 'probable' | 'to_verify'
export type ImpactLevel = 'high' | 'medium' | 'low'
export type VisualizationType = 'line' | 'bar' | 'stackedBar' | 'pie' | 'table'
export type ReportExportFormat = 'html' | 'md' | 'json'

export interface ReportProblemDefinition {
  question: string
  scope: string
  metric: string
  baseline: string
  scenario: ReportScenario
  assumptions: string[]
}

export interface KeyMetric {
  metric_id: string
  label: string
  value: number
  unit: string | null
  formula: string
  scope: string
  baseline_value: number | null
  absolute_change: number | null
  change_rate: number | null
}

export interface EvidenceItem {
  evidence_id: string
  title: string
  description: string
  evidence_type: string
  metric: string | null
  current_value: number | null
  baseline_value: number | null
  change_value: number | null
  change_rate: number | null
  scope: string
  source_file_ids: string[]
  formula: string
  quality_status: 'verified' | 'limited'
}

export interface AttributionConclusion {
  conclusion_id: string
  title: string
  description: string
  status: ConclusionStatus
  impact_level: ImpactLevel
  confidence: number
  evidence_ids: string[]
  verification_needed: boolean
}

export interface MissingDataItem {
  field: string
  reason: string
  impact: string
  required_action: string
}

export interface NextAction {
  action_id: string
  title: string
  description: string
  priority: ImpactLevel
  owner_hint: string | null
}

export interface ChartSeries {
  name: string
  data: number[]
}

export interface Visualization {
  chart_id: string
  title: string
  type: VisualizationType
  dimension: string | null
  categories: string[]
  series: ChartSeries[]
  columns: string[]
  rows: Record<string, unknown>[]
}

export interface ReportIR {
  schema_version: string
  task_id: string
  problem_definition: ReportProblemDefinition
  key_metrics: KeyMetric[]
  evidence_list: EvidenceItem[]
  attribution_conclusions: AttributionConclusion[]
  missing_data: MissingDataItem[]
  next_actions: NextAction[]
  visualizations: Visualization[]
}

export interface GeneratedFileItem {
  file_id: string
  file_type: ReportExportFormat
  file_name: string
  file_size: number
  download_url: string
}

export interface AnalysisResult {
  task_id: string
  result_id: string
  schema_version: string
  problem_definition: ReportProblemDefinition
  key_metrics: KeyMetric[]
  evidence_list: EvidenceItem[]
  attribution_conclusions: AttributionConclusion[]
  conclusion_text: string
  missing_data_text: string
  next_actions: NextAction[]
  result_markdown: string
  result_file_path: string | null
  report_ir: ReportIR
  generated_files: GeneratedFileItem[]
  validation_status: string
}
