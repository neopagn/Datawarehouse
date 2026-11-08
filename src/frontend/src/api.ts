export interface Offering {
  offering_key: number
  domain: string
  code_module: string
  code_presentation: string
  length_weeks: number
}

export interface Meta {
  run_id: number
  offerings: Offering[]
}

export type Concept = 'clicks' | 'silence' | 'missed' | 'score'

export interface Student {
  rank: number
  id_student: number
  risk: number
  silent: boolean
  clicks_cum: number
  days_since_last_activity: number | null
  missed_cum: number
  due_cum: number
  score_lagged: number | null
  reasons: { concept: Concept; push: number }[]
}

export interface Selection {
  module: string
  presentation: string
  week: number
}

export interface StudentsPayload {
  run_id: number
  week: number
  cutoff_day: number
  students: Student[]
}

export type BaselineName = 'missed' | 'silence' | 'clicks'

export interface Leavers {
  enrollments: number
  left_before_first_cutoff: number
  left_before_cutoff: number
}

export interface CurvePayload {
  baseline: BaselineName
  enrolled: number
  at_risk: number
  leavers: Leavers
  tp_model: number[]
  tp_baseline: number[]
}

export type Precision = Record<'model' | BaselineName, Record<string, number>>

export interface GroupResult {
  offerings: number
  rows: number
  base_rate: number
  precision: Precision
  precision_without_silent: Precision
}

export interface OfferingResult {
  rows: number
  at_risk: number
  base_rate: number
  silent_rows: number
  precision: Precision
  precision_without_silent: Precision
}

export interface CalibrationBin {
  rows: number
  predicted: number
  observed: number
}

export interface SensitivityResult {
  offerings: number
  rows: number
  precision: Precision
}

export interface WeekEvaluation {
  frozen_baseline: BaselineName
  groups: Record<string, GroupResult>
  offerings: Record<string, OfferingResult>
  calibration: { excluding_ccc: CalibrationBin[]; ccc: CalibrationBin[] }
  sensitivity: Record<'no_score_lag' | 'without_repeat_students' | 'train_2013b_test_2014b', SensitivityResult>
  repeat_rows: number
  test_rows: number
}

export interface Evaluation {
  weeks: Record<string, WeekEvaluation>
}

export interface ModelWeek {
  concepts: Concept[]
  c: number
  cv_precision: number
  baseline: BaselineName
  baseline_cv_precision: Record<BaselineName, number>
  rows: number
  at_risk: number
  coefficients: Record<string, number>
}

export interface ModelDescription {
  train_offerings: string[]
  served_year: string
  weeks: Record<string, ModelWeek>
  leavers: Leavers
}

export interface EnrollmentMetrics {
  enrollments: number
  students: number
  at_risk: number
  withdrawn: number
  risk_pct: number | null
  withdrawn_pct: number | null
}

export interface RollupRow extends EnrollmentMetrics {
  domain: string | null
  code_module: string | null
  code_presentation: string | null
  grouping: number
}

export interface OverviewTables {
  summary: EnrollmentMetrics
  rollup: RollupRow[]
  breakdowns: Record<'imd' | 'education' | 'disability', (EnrollmentMetrics & { label: string | null })[]>
  attempts: (EnrollmentMetrics & { previous_attempts: number })[]
}

export interface RegistrationTables {
  summary: EnrollmentMetrics & {
    known_unregistration: number
    unknown_unregistration: number
    na_unregistration: number
  }
  cancellations: { phase: string; enrollments: number; share_pct: number | null }[]
  registrations: (EnrollmentMetrics & { phase: string })[]
}

export interface WeekMetrics {
  enrollments: number
  avg_clicks: number | null
  zero_click: number
  zero_click_pct: number | null
  avg_missed: number | null
  at_risk: number
  risk_pct: number | null
}

export interface EngagementTables {
  summary: WeekMetrics
  outcomes: (WeekMetrics & { final_result: string })[]
  activity: { activity_group: string; activity_type: string | null; grouping: number; clicks: number; share_pct: number | null }[]
  trend: { week_no: number; final_result: string; enrollments: number; avg_clicks: number | null }[]
}

export interface AssessmentMetrics {
  records: number
  banked: number
  scored: number
  avg_score: number | null
  below_40: number
  below_40_pct: number | null
  eligible_late: number
  late: number
  late_pct: number | null
}

export interface AssessmentDetail extends AssessmentMetrics {
  id_assessment: number
  code_module: string
  code_presentation: string
  assessment_type: string
  effective_due_day: number | null
  is_due_estimated: boolean
  is_formative: boolean
  has_recorded_results: boolean
  weight: number | null
  enrollments: number
  record_pct: number | null
}

export interface AssessmentsTables {
  by_type: (AssessmentMetrics & { assessment_type: string; assessments: number })[]
  detail: AssessmentDetail[]
}

export interface SignalsTables {
  summary: WeekMetrics
  buckets: (WeekMetrics & { missed_bucket: number })[]
}

export interface ScreenTables {
  overview: OverviewTables
  registration: RegistrationTables
  engagement: EngagementTables
  assessments: AssessmentsTables
  signals: SignalsTables
}

export type Screen = keyof ScreenTables

export interface ScreenPayload<S extends Screen> {
  run_id: number
  loaded_at: string
  elapsed_seconds: number
  selected_count: number
  week_coverage: number | null
  tables: ScreenTables[S]
}

export interface ScreenFilters {
  domain: string | null
  module: string | null
  presentation: string | null
  week?: number
}

export class ApiError extends Error {
  constructor(readonly code: string, message: string) {
    super(message)
  }
}

type Params = Record<string, string | number | null | undefined>

async function getJson<T>(path: string, params: Params, signal?: AbortSignal): Promise<T> {
  const present = Object.entries(params).filter(([, value]) => value !== null && value !== undefined)
  const query = new URLSearchParams(present.map(([key, value]) => [key, String(value)]))
  const response = await fetch(`${path}?${query}`, { signal })
  if (response.ok) return response.json() as Promise<T>
  const body = await response.json().catch(() => null)
  throw new ApiError(body?.error?.code ?? 'internal', body?.error?.message ?? 'Không tải được dữ liệu kho.')
}

export const fetchMeta = (signal?: AbortSignal) => getJson<Meta>('/api/meta', {}, signal)

export const fetchEvaluation = (signal?: AbortSignal) => getJson<Evaluation>('/api/dss/evaluation', {}, signal)

export const fetchModel = (signal?: AbortSignal) => getJson<ModelDescription>('/api/dss/model', {}, signal)

export const fetchScreen = <S extends Screen>(screen: S, filters: ScreenFilters, runId: number, signal?: AbortSignal) =>
  getJson<ScreenPayload<S>>(`/api/screens/${screen}`, { ...filters, expected_run_id: runId }, signal)

function checkpointParams({ module, presentation, week }: Selection, runId: number) {
  return { module, presentation, week, expected_run_id: runId }
}

export const fetchStudents = (selection: Selection, runId: number, signal?: AbortSignal) =>
  getJson<StudentsPayload>('/api/dss/students', checkpointParams(selection, runId), signal)

export const fetchCurve = (selection: Selection, runId: number, signal?: AbortSignal) =>
  getJson<CurvePayload>('/api/dss/curve', checkpointParams(selection, runId), signal)
