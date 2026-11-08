import type { BaselineName, Concept, Precision, Student } from './api'

export const SHARES = ['5', '10', '20', '30'] as const
export const MAX_CONTACT_SHARE = 0.3
const CURVE_SHARE = 0.4

const integer = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 })
const decimal = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })
const ratio = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

export const formatCount = (value: number) => integer.format(value)
export const formatDecimal = (value: number) => decimal.format(value)
/** Exact percentage from counts: rounding the API's 2-decimal rate again would turn 53,349 into 53,4. */
export const ratePct = (part: number, whole: number) => (whole ? (100 * part) / whole : null)

export const formatPercent = (value: number) => `${ratio.format(value * 100)}%`

export const BASELINE_LABELS: Record<BaselineName, string> = {
  missed: 'Bỏ lỡ nhiều nhất',
  silence: 'Im lâu nhất',
  clicks: 'Click ít nhất',
}

export function maxContacts(enrolled: number) {
  return Math.max(1, Math.ceil(enrolled * MAX_CONTACT_SHARE))
}

/** Keeps the contact budget proportional when the cohort size changes. */
export function rescaleContacts(contacts: number, previous: number, next: number) {
  if (previous === 0) return Math.max(1, Math.ceil(next * 0.1))
  return Math.min(maxContacts(next), Math.max(1, Math.round((contacts / previous) * next)))
}

/** Extra at-risk students reached by the model, scaled by an assumed, unmeasured effect. */
export function estimatedImpact(modelTp: number, baselineTp: number, efficacy: number) {
  return (modelTp - baselineTp) * efficacy
}

export function reasonLabel(concept: Concept, student: Student) {
  switch (concept) {
    case 'silence':
      return student.days_since_last_activity === null ? 'Chưa hoạt động' : `Im ${student.days_since_last_activity} ngày`
    case 'missed':
      return `Bỏ ${student.missed_cum}/${student.due_cum} bài`
    case 'clicks':
      return `${formatCount(student.clicks_cum)} click`
    case 'score':
      return student.score_lagged === null ? 'Chưa có điểm' : `Điểm ${formatDecimal(student.score_lagged)}`
  }
}

/** Offerings where the model is at least as precise as every baseline, compared on one share. */
export function offeringsWon(results: { precision: Precision }[], share: string) {
  return results.filter(({ precision }) => {
    const model = precision.model[share] ?? 0
    return (['missed', 'silence', 'clicks'] as const).every((name) => model >= (precision[name][share] ?? 0))
  }).length
}

/** The chart runs a little past the slider's limit, so the selection never sits on the edge. */
export function curveDomain(enrolled: number) {
  return Math.ceil(enrolled * CURVE_SHARE)
}

/** Expected at-risk students reached by contacting at random. */
export function randomReached(contacts: number, atRisk: number, enrolled: number) {
  return enrolled ? (contacts * atRisk) / enrolled : 0
}

/** Pushes line-end labels down until none overlap; input and output keep their order. */
export function separateLabels(positions: number[], gap: number) {
  const order = positions.map((_, index) => index).sort((a, b) => (positions[a] ?? 0) - (positions[b] ?? 0))
  const result = [...positions]
  order.forEach((index, step) => {
    const above = order[step - 1]
    if (above !== undefined) result[index] = Math.max(result[index] ?? 0, (result[above] ?? 0) + gap)
  })
  return result
}
