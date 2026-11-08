import { useState } from 'react'
import type { Offering } from './api'
import { HBars, referenceLine, type BarRow } from './charts'
import { formatCount, formatDecimal, ratePct } from './decision-logic'
import {
  cleanPhase, deepestLevel, LEVEL_GROUPING, levelAllowed, withDomain, withModule, withPresentation, type Level, type Scope,
} from './scope-logic'
import { Info, LoadError, Loading, ScopeFilters, Segmented, Stat } from './ui-parts'
import { useScreen } from './use-screen'

type View = 'results' | 'groups' | 'timing'
type Dimension = 'imd' | 'education' | 'disability' | 'attempts'

const VIEWS: { key: View; label: string }[] = [
  { key: 'results', label: 'Kết quả · Q1' },
  { key: 'groups', label: 'Nhóm sinh viên · Q1, Q5' },
  { key: 'timing', label: 'Thời điểm rút · Q2' },
]
const DIMENSIONS: { key: Dimension; label: string }[] = [
  { key: 'imd', label: 'IMD' },
  { key: 'education', label: 'Trình độ' },
  { key: 'disability', label: 'Khuyết tật' },
  { key: 'attempts', label: 'Số lần học trước · Q5' },
]
const ATTEMPT_LABELS = ['0 lần', '1 lần', 'Từ 2 lần']
const DISABILITY_LABELS: Record<string, string> = { Y: 'Có khuyết tật', N: 'Không khuyết tật' }
const LEVEL_LABELS: Record<Level, string> = { domain: 'Lĩnh vực', module: 'Module', presentation: 'Lần mở' }
const percent = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${formatDecimal(value)}%`)
const enrollments = (value: number) => `${formatCount(value)} lượt`

interface Props {
  offerings: Offering[]
  runId: number
  scope: Scope
  onScope: (scope: Scope) => void
}

export function SituationChapter({ offerings, runId, scope, onScope }: Props) {
  const [view, setView] = useState<View>('results')
  return (
    <main className="chapter situation">
      <div className="toolbar">
        <ScopeFilters offerings={offerings} scope={scope} onChange={onScope} />
        <Segmented label="Góc nhìn" options={VIEWS} value={view} onChange={setView} />
      </div>
      {view === 'results' && <Results {...{ offerings, runId, scope, onScope }} />}
      {view === 'groups' && <Groups runId={runId} scope={scope} />}
      {view === 'timing' && <Timing runId={runId} scope={scope} />}
    </main>
  )
}

function Results({ offerings, runId, scope, onScope }: Props) {
  const { payload, error, loading, retry } = useScreen('overview', scope, undefined, runId)
  const [picked, setPicked] = useState<Level | null>(null)
  const level = picked && levelAllowed(picked, scope) ? picked : deepestLevel(scope)
  if (error) return <LoadError error={error} retry={retry} />
  if (!payload) return <Loading />
  const { summary, rollup } = payload.tables

  function drill(next: Scope) {
    setPicked(null)
    onScope(next)
  }

  const rows: BarRow[] = rollup.filter((row) => row.grouping === LEVEL_GROUPING[level]).map((row) => {
    const label = level === 'domain' ? row.domain : level === 'module' ? row.code_module : row.code_presentation
    const onClick = level === 'domain' ? () => drill(withDomain(row.domain))
      : level === 'module' ? () => drill(withModule(offerings, scope, row.code_module))
        : scope.presentation ? undefined : () => drill(withPresentation(scope, row.code_presentation))
    return { key: label ?? '', label: label ?? '—', value: ratePct(row.at_risk, row.enrollments), note: enrollments(row.enrollments), onClick }
  })
  // Presentations stay in time order: ranking them would read as a cross-term league table.
  if (level !== 'presentation') rows.sort((a, b) => (b.value ?? 0) - (a.value ?? 0))

  const passed = summary.enrollments - summary.at_risk
  const failed = summary.at_risk - summary.withdrawn
  const share = (value: number) => `${(value / Math.max(summary.enrollments, 1)) * 100}%`
  const crumbs: { label: string; target: Scope }[] = [
    { label: 'Toàn kho', target: withDomain(null) },
    ...(scope.domain ? [{ label: scope.domain, target: withDomain(scope.domain) }] : []),
    ...(scope.module ? [{ label: scope.module, target: withModule(offerings, scope, scope.module) }] : []),
    ...(scope.presentation ? [{ label: scope.presentation, target: scope }] : []),
  ]

  return (
    <div className="view split results" aria-busy={loading}>
      <section className="hero">
        <span className="muted">Kết thúc bằng Fail hoặc Withdrawn<Info>Fail + Withdrawn trên số lượt ghi danh, không phải số sinh viên. Đây là kết quả toàn khóa, không phải dự báo.</Info></span>
        <strong className="hero-number">{percent(ratePct(summary.at_risk, summary.enrollments))}</strong>
        <div className="stack" role="img" aria-label={`Đạt ${passed}, Withdrawn ${summary.withdrawn}, Fail ${failed}`}>
          <i className="pass" style={{ width: share(passed) }} />
          <i className="withdrawn" style={{ width: share(summary.withdrawn) }} />
          <i className="fail" style={{ width: share(failed) }} />
        </div>
        <ul className="stack-legend">
          <li><i className="pass" />Đạt {formatCount(passed)}</li>
          <li><i className="withdrawn" />Withdrawn {formatCount(summary.withdrawn)}</li>
          <li><i className="fail" />Fail {formatCount(failed)}</li>
        </ul>
        <div className="stats">
          <Stat label="Lượt ghi danh" value={formatCount(summary.enrollments)} />
          <Stat label="Sinh viên" value={formatCount(summary.students)} info="Sinh viên phân biệt. Một người có thể có nhiều lượt." />
          <Stat label="At-risk" value={formatCount(summary.at_risk)} />
          <Stat label="Tỉ lệ Withdrawn" value={percent(ratePct(summary.withdrawn, summary.enrollments))} />
        </div>
      </section>
      <section className="panel-block">
        <header className="block-head">
          <nav className="crumbs" aria-label="Roll-up">
            {crumbs.map((crumb, index) => (index === crumbs.length - 1
              ? <span key={crumb.label} aria-current="location">{crumb.label}</span>
              : <button key={crumb.label} onClick={() => drill(crumb.target)}>{crumb.label}</button>))}
          </nav>
          <Segmented label="Cấp phân tích" value={level} onChange={setPicked}
            options={(Object.keys(LEVEL_LABELS) as Level[]).filter((key) => levelAllowed(key, scope)).map((key) => ({ key, label: LEVEL_LABELS[key] }))} />
          <Info>Bấm một dòng để drill-down, bấm đường dẫn để roll-up. Tỉ lệ tính lại ở từng cấp, không lấy trung bình cấp con. Lần mở chỉ so trong cùng module.</Info>
        </header>
        <HBars rows={rows} unit="%" max={100} reference={referenceLine(ratePct(summary.at_risk, summary.enrollments), 'Phạm vi')} />
      </section>
    </div>
  )
}

function Groups({ runId, scope }: { runId: number; scope: Scope }) {
  const { payload, error, loading, retry } = useScreen('overview', scope, undefined, runId)
  const [dimension, setDimension] = useState<Dimension>('imd')
  if (error) return <LoadError error={error} retry={retry} />
  if (!payload) return <Loading />
  const { summary, breakdowns, attempts } = payload.tables
  const rows: BarRow[] = dimension === 'attempts'
    ? attempts.map((row) => ({ key: String(row.previous_attempts), label: ATTEMPT_LABELS[row.previous_attempts] ?? String(row.previous_attempts), value: ratePct(row.at_risk, row.enrollments), note: enrollments(row.enrollments) }))
    : breakdowns[dimension].map((row) => {
      const label = row.label ?? 'Unknown'
      return { key: label, label: dimension === 'disability' ? DISABILITY_LABELS[label] ?? label : label, value: ratePct(row.at_risk, row.enrollments), note: enrollments(row.enrollments) }
    })
  return (
    <div className="view" aria-busy={loading}>
      <section className="panel-block">
        <header className="block-head">
          <h2>Tỉ lệ Fail + Withdrawn</h2>
          <Segmented label="Chiều phân nhóm" options={DIMENSIONS} value={dimension} onChange={setDimension} />
          <Info>Chiều phân nhóm chỉ đổi biểu đồ này, không phải bộ lọc chung. IMD 0–10% là khu vực khó khăn nhất; Unknown là dữ liệu thiếu thật. Mỗi tỉ lệ dùng mẫu số của chính nhóm đó. Tương quan, không phải nguyên nhân.</Info>
        </header>
        <HBars rows={rows} unit="%" max={100} reference={referenceLine(ratePct(summary.at_risk, summary.enrollments), 'Phạm vi')} />
      </section>
    </div>
  )
}

function Timing({ runId, scope }: { runId: number; scope: Scope }) {
  const { payload, error, loading, retry } = useScreen('registration', scope, undefined, runId)
  if (error) return <LoadError error={error} retry={retry} />
  if (!payload) return <Loading />
  const { summary, cancellations, registrations } = payload.tables
  const early = cancellations.filter((row) => /Trước khai giảng|Ngày 0/.test(row.phase)).reduce((total, row) => total + row.enrollments, 0)
  return (
    <div className="view split even" aria-busy={loading}>
      <section className="panel-block">
        <header className="block-head">
          <h2>Ngày hủy đã biết</h2>
          <Info>Mẫu số chỉ gồm lượt có ngày hủy đã biết, kể cả lượt có nhãn cuối khác Withdrawn. Không biểu diễn toàn bộ Withdrawn.</Info>
        </header>
        {summary.known_unregistration > 0 && (
          <p className="headline"><b>{formatDecimal((100 * early) / summary.known_unregistration)}%</b> hủy trước hoặc đúng ngày khai giảng</p>
        )}
        <HBars unit="%" max={100} rows={cancellations.map((row) => ({ key: row.phase, label: cleanPhase(row.phase), value: ratePct(row.enrollments, summary.known_unregistration), note: enrollments(row.enrollments) }))} />
        <div className="stats">
          <Stat label="Withdrawn" value={formatCount(summary.withdrawn)} />
          <Stat label="Ngày hủy đã biết" value={formatCount(summary.known_unregistration)} />
          <Stat label="Không rõ" value={formatCount(summary.unknown_unregistration)} info="Withdrawn nhưng thiếu ngày hủy trong nguồn." />
          <Stat label="Không áp dụng" value={formatCount(summary.na_unregistration)} info="Lượt không hủy nên không có ngày hủy." />
        </div>
      </section>
      <section className="panel-block">
        <header className="block-head">
          <h2>Thời điểm đăng ký và tỉ lệ Withdrawn</h2>
          <Info>Mỗi tỉ lệ dùng mẫu số của nhóm đăng ký đó. Nhóm nhỏ có thể cho tỉ lệ cực đoan: xem số lượt bên cạnh.</Info>
        </header>
        <HBars unit="%" max={100} reference={referenceLine(ratePct(summary.withdrawn, summary.enrollments), 'Phạm vi')}
          rows={registrations.map((row) => ({ key: row.phase, label: cleanPhase(row.phase), value: ratePct(row.withdrawn, row.enrollments), note: enrollments(row.enrollments) }))} />
      </section>
    </div>
  )
}
