import { useMemo, useState } from 'react'
import type { AssessmentDetail, Offering } from './api'
import { HBars, LineChart, referenceLine, type Series } from './charts'
import { formatCount, formatDecimal, ratePct } from './decision-logic'
import { examScoreComparable, reachableWeek, selectedOfferings, type Scope } from './scope-logic'
import { Info, LoadError, Loading, ScopeFilters, Segmented, Stat, WeekControl } from './ui-parts'
import { useScreen } from './use-screen'

type View = 'clicks' | 'resources' | 'assessments' | 'missed'

const VIEWS: { key: View; label: string }[] = [
  { key: 'clicks', label: 'Click · Q3' },
  { key: 'resources', label: 'Tài nguyên' },
  { key: 'assessments', label: 'Bài đánh giá · Q4' },
  { key: 'missed', label: 'Bài bỏ lỡ · Q6' },
]
const OUTCOME_ORDER = ['Distinction', 'Pass', 'Fail', 'Withdrawn']
const OUTCOME_COLORS: Record<string, string> = { Distinction: '#3f8ae0', Pass: '#23a07f', Fail: '#e26b30', Withdrawn: '#d060b8' }
const TYPE_COLORS: Record<string, string> = { TMA: '#3f8ae0', CMA: '#23a07f' }
const MISSED_LABELS = ['0 bài', '1 bài', 'Từ 2 bài']
const number = (value: number | null | undefined) => (value === null || value === undefined ? '—' : formatDecimal(value))
const percent = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${formatDecimal(value)}%`)
const enrollments = (value: number) => `${formatCount(value)} lượt`
const RETROSPECTIVE = <>Tương quan hồi cứu với kết quả cuối khóa. Không phải dự báo, không phải bằng chứng hiệu quả can thiệp.</>
const SNAPSHOT = <>Snapshot gồm lượt còn ghi danh tại cuối tuần, kể cả tuần không click. Withdrawn thiếu ngày hủy vẫn có thể nằm trong snapshot.</>

interface Props {
  offerings: Offering[]
  runId: number
  scope: Scope
  onScope: (scope: Scope) => void
}

export function SignalsChapter({ offerings, runId, scope, onScope }: Props) {
  const [view, setView] = useState<View>('clicks')
  const [chosenWeek, setWeek] = useState(7)
  const selected = useMemo(() => selectedOfferings(offerings, scope), [offerings, scope])
  const week = reachableWeek(chosenWeek, selected)
  const usesWeek = view !== 'assessments'
  const common = { runId, scope, week }
  const coverage = usesWeek ? { covered: selected.filter((row) => row.length_weeks > week).length, selected: selected.length } : null
  return (
    <main className="chapter">
      <div className="toolbar">
        <ScopeFilters offerings={offerings} scope={scope} onChange={onScope} />
        {usesWeek && <WeekControl offerings={offerings} scope={scope} week={week} onChange={setWeek} coverage={coverage} />}
        <Segmented label="Góc nhìn" options={VIEWS} value={view} onChange={setView} />
      </div>
      {view === 'clicks' && <Clicks {...common} onWeek={setWeek} />}
      {view === 'resources' && <Resources {...common} />}
      {view === 'assessments' && <Assessments runId={runId} scope={scope} selected={selected} />}
      {view === 'missed' && <Missed {...common} />}
    </main>
  )
}

interface ViewProps {
  runId: number
  scope: Scope
  week: number
}

function Clicks({ runId, scope, week, onWeek }: ViewProps & { onWeek: (week: number) => void }) {
  const { payload, error, loading, retry } = useScreen('engagement', scope, week, runId)
  const series = useMemo<Series[]>(() => OUTCOME_ORDER.map((outcome) => ({
    key: outcome, label: outcome, color: OUTCOME_COLORS[outcome] ?? '',
    points: (payload?.tables.trend ?? []).filter((row) => row.final_result === outcome && row.avg_clicks !== null)
      .map((row) => ({ x: row.week_no, y: row.avg_clicks as number })),
  })), [payload])
  if (error) return <LoadError error={error} retry={retry} />
  if (!payload) return <Loading />
  const { summary, outcomes } = payload.tables
  const ordered = OUTCOME_ORDER.flatMap((name) => outcomes.filter((row) => row.final_result === name))
  return (
    <div className="view split wide" aria-busy={loading}>
      <section className="panel-block grow">
        <header className="block-head">
          <h2>Click trung bình mỗi lượt, theo tuần</h2>
          <span className="tag">Hồi cứu</span>
          <Info>{RETROSPECTIVE} Chỉ gồm tuần mọi lần mở đã chọn đều có; bỏ điểm dưới 20 lượt. Bấm trên biểu đồ để chọn tuần.</Info>
        </header>
        <LineChart series={series} xLabel="Tuần" yLabel="Click TB / lượt" cursor={week} onPick={onWeek} />
      </section>
      <section className="panel-block">
        <header className="block-head">
          <h2>Snapshot tuần {week}</h2>
          <Info>{SNAPSHOT}</Info>
        </header>
        <div className="stats">
          <Stat label="Lượt còn học" value={formatCount(summary.enrollments)} />
          <Stat label="Click TB" value={number(summary.avg_clicks)} />
          <Stat label="Không click" value={percent(ratePct(summary.zero_click, summary.enrollments))} />
          <Stat label="Bài bỏ lỡ TB" value={number(summary.avg_missed)} />
        </div>
        <table className="data">
          <thead><tr><th scope="col">Kết quả</th><th scope="col">Lượt</th><th scope="col">Click TB</th><th scope="col">Không click</th><th scope="col">Bỏ lỡ TB</th></tr></thead>
          <tbody>
            {ordered.map((row) => (
              <tr key={row.final_result}>
                <th scope="row"><i className="key" style={{ background: OUTCOME_COLORS[row.final_result] }} />{row.final_result}</th>
                <td>{formatCount(row.enrollments)}</td><td>{number(row.avg_clicks)}</td><td>{percent(ratePct(row.zero_click, row.enrollments))}</td><td>{number(row.avg_missed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

function Resources({ runId, scope, week }: ViewProps) {
  const { payload, error, loading, retry } = useScreen('engagement', scope, week, runId)
  const [group, setGroup] = useState<string | null>(null)
  if (error) return <LoadError error={error} retry={retry} />
  if (!payload) return <Loading />
  const groups = payload.tables.activity.filter((row) => row.grouping === 1)
  const openGroup = group !== null && groups.some((row) => row.activity_group === group) ? group : null
  const rows = payload.tables.activity
    .filter((row) => (openGroup === null ? row.grouping === 1 : row.grouping === 0 && row.activity_group === openGroup))
    .sort((a, b) => b.clicks - a.clicks)
    .map((row) => {
      const label = (openGroup === null ? row.activity_group : row.activity_type) ?? '—'
      return { key: label, label, value: row.share_pct, note: `${formatCount(row.clicks)} click`, onClick: openGroup === null ? () => setGroup(row.activity_group) : undefined }
    })
  return (
    <div className="view" aria-busy={loading}>
      <section className="panel-block">
        <header className="block-head">
          <nav className="crumbs" aria-label="Roll-up tài nguyên">
            {openGroup === null
              ? <span aria-current="location">Mọi nhóm tài nguyên</span>
              : <button onClick={() => setGroup(null)}>Mọi nhóm tài nguyên</button>}
            {openGroup && <span aria-current="location">{openGroup}</span>}
          </nav>
          <Info>Click sự kiện trong tuần từ aggregate, có thể gồm click của lượt đã hủy, nên không chia cho số lượt snapshot. Tỉ trọng luôn tính trên tổng click của phạm vi và tuần, kể cả khi drill-down.</Info>
        </header>
        {rows.length ? <HBars rows={rows} unit="%" /> : <p className="muted">Không có click trong tuần này.</p>}
      </section>
    </div>
  )
}

function Assessments({ runId, scope, selected }: { runId: number; scope: Scope; selected: Offering[] }) {
  const { payload, error, loading, retry } = useScreen('assessments', scope, undefined, runId)
  const [type, setType] = useState('all')
  if (error) return <LoadError error={error} retry={retry} />
  if (!payload) return <Loading />
  const { by_type: byType, detail } = payload.tables
  const examScores = examScoreComparable(selected)
  const shownScore = (row: { assessment_type: string; avg_score: number | null }) => (row.assessment_type === 'Exam' && !examScores ? null : row.avg_score)
  const types = [...new Set(detail.map((row) => row.assessment_type))].sort()
  const series: Series[] = Object.keys(TYPE_COLORS).map((name) => ({
    key: name, label: name, color: TYPE_COLORS[name] ?? '',
    points: detail.filter((row) => row.assessment_type === name && row.record_pct !== null && row.effective_due_day !== null)
      .map((row) => ({ x: row.effective_due_day as number, y: row.record_pct as number })),
  }))
  const visible = detail.filter((row) => type === 'all' || row.assessment_type === type)
  return (
    <div className="view assessments" aria-busy={loading}>
      <section className="panel-block">
        <header className="block-head">
          <h2>Theo loại bài</h2>
          <Info>Điểm TB gồm banked, điểm thiếu không thành 0. Trễ chỉ tính TMA/CMA không banked. CMA ở BBB, CCC, DDD gần như luôn sau hạn trong dữ liệu nguồn, đừng đọc như trễ thật. Banked: điểm chuyển từ lần học trước.</Info>
        </header>
        <table className="data">
          <thead><tr><th scope="col">Loại</th><th scope="col">Số bài</th><th scope="col">Bản ghi</th><th scope="col">Banked</th><th scope="col">Điểm TB</th><th scope="col">Dưới 40</th><th scope="col">Trễ</th></tr></thead>
          <tbody>
            {byType.map((row) => (
              <tr key={row.assessment_type}>
                <th scope="row">{row.assessment_type}{row.assessment_type === 'Exam' && !examScores && <Info label="Vì sao ẩn điểm Exam">Chỉ CCC và DDD có điểm Exam được ghi nhận. Chọn CCC hoặc DDD để xem. Thiếu điểm không có nghĩa là 0 hoặc không nộp.</Info>}</th>
                <td>{formatCount(row.assessments)}</td><td>{formatCount(row.records)}</td><td>{formatCount(row.banked)}</td>
                <td>{number(shownScore(row))}</td><td>{row.assessment_type === 'Exam' && !examScores ? '—' : percent(ratePct(row.below_40, row.scored))}</td><td>{percent(ratePct(row.late, row.eligible_late))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <header className="block-head">
          <h2>Đường rơi qua từng bài</h2>
          <Info>Bản ghi / lượt ghi danh theo ngày hạn, không gồm Exam, gồm banked. Đường giảm gợi ý bỏ dở, không chứng minh nguyên nhân.</Info>
        </header>
        {selected.length === 1
          ? <LineChart series={series} xLabel="Ngày hạn" yLabel="Có bản ghi (%)" dots yMax={100} />
          : <p className="prompt">Chọn module và một lần mở để xem đường rơi: lịch bài khác nhau nên không gộp.</p>}
      </section>
      <section className="panel-block">
        <header className="block-head">
          <h2>Chi tiết từng bài</h2>
          <Segmented label="Loại bài" value={type} onChange={setType}
            options={[{ key: 'all', label: 'Tất cả' }, ...types.map((name) => ({ key: name, label: name }))]} />
          <Info>F: formative, trọng số 0. ~: ngày hạn ước tính. ∅: không có kết quả ghi nhận, không chứng minh sinh viên không nộp.</Info>
        </header>
        <div className="scroll">
          <table className="data">
            <thead><tr><th scope="col">Bài</th><th scope="col">Lần mở</th><th scope="col">Hạn</th><th scope="col">Trọng số</th><th scope="col">Có bản ghi</th><th scope="col">Điểm TB</th><th scope="col">Dưới 40</th><th scope="col">Trễ</th></tr></thead>
            <tbody>{visible.map((row) => <DetailRow key={row.id_assessment} row={row} score={shownScore(row)} />)}</tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function DetailRow({ row, score }: { row: AssessmentDetail; score: number | null }) {
  const marks = `${row.is_formative ? ' F' : ''}${row.is_due_estimated ? ' ~' : ''}${row.has_recorded_results ? '' : ' ∅'}`
  return (
    <tr>
      <th scope="row">{row.assessment_type} {row.id_assessment}<em>{marks}</em></th>
      <td>{row.code_module}·{row.code_presentation}</td><td>{row.effective_due_day ?? '—'}</td><td>{row.weight ?? '—'}</td>
      <td>{percent(ratePct(row.records, row.enrollments))}</td><td>{number(score)}</td><td>{percent(ratePct(row.below_40, row.scored))}</td><td>{percent(ratePct(row.late, row.eligible_late))}</td>
    </tr>
  )
}

function Missed({ runId, scope, week }: ViewProps) {
  const signals = useScreen('signals', scope, week, runId)
  const overview = useScreen('overview', scope, undefined, runId)
  const failure = signals.error ?? overview.error
  if (failure) return <LoadError error={failure} retry={() => { signals.retry(); overview.retry() }} />
  if (!signals.payload || !overview.payload) return <Loading />
  const { summary, buckets } = signals.payload.tables
  const whole = overview.payload.tables.summary
  return (
    <div className="view split wide" aria-busy={signals.loading}>
      <section className="panel-block">
        <header className="block-head">
          <h2>Bài bỏ lỡ tới tuần {week} và kết quả cuối khóa</h2>
          <span className="tag">Hồi cứu</span>
          <Info>{RETROSPECTIVE} Nhóm 0, 1 và từ 2 bài là rời nhau. Không xếp hạng cá nhân ở màn này; xếp hạng thuộc Chương 3.</Info>
        </header>
        <HBars unit="%" max={100} reference={referenceLine(ratePct(summary.at_risk, summary.enrollments), 'Tỉ lệ nền')}
          rows={buckets.map((row) => ({ key: String(row.missed_bucket), label: MISSED_LABELS[row.missed_bucket] ?? '', value: ratePct(row.at_risk, row.enrollments), note: enrollments(row.enrollments) }))} />
      </section>
      <section className="panel-block">
        <header className="block-head">
          <h2>Cùng tỉ lệ, khác mẫu số</h2>
          <Info>Sinh viên hủy trước mốc rời khỏi snapshot, nên tỉ lệ nền của snapshot thấp hơn tỉ lệ toàn bộ lượt. Hai số đúng cho hai câu hỏi khác nhau.</Info>
        </header>
        <div className="denominators">
          <div><span className="muted">Toàn bộ lượt</span><strong>{percent(ratePct(whole.at_risk, whole.enrollments))}</strong><span className="muted">{formatCount(whole.at_risk)} / {formatCount(whole.enrollments)}</span></div>
          <div><span className="muted">Snapshot tuần {week}</span><strong>{percent(ratePct(summary.at_risk, summary.enrollments))}</strong><span className="muted">{formatCount(summary.at_risk)} / {formatCount(summary.enrollments)}</span></div>
        </div>
      </section>
    </div>
  )
}

