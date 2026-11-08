import { memo, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError, fetchCurve, fetchStudents, type CurvePayload, type Offering, type Selection, type Student, type StudentsPayload,
} from './api'
import {
  BASELINE_LABELS, estimatedImpact, formatCount, formatDecimal, maxContacts, reasonLabel, rescaleContacts,
} from './decision-logic'
import { EvaluationPanel } from './evaluation-panel'
import { GainCurve } from './gain-curve'
import { ModelPanel } from './model-panel'
import { Info, LoadError } from './ui-parts'
import { StatusContext } from './use-screen'

const WEEKS = [3, 7, 11]
const EFFICACY_LEVELS = [0.1, 0.2, 0.3, 0.5]

interface Loaded {
  key: string
  students: StudentsPayload
  curve: CurvePayload
}

const ContactRow = memo(function ContactRow({ student }: { student: Student }) {
  return (
    <li>
      <span className="rank">{student.rank}</span>
      <span className="id">{student.id_student}</span>
      <span className="reasons">
        {student.reasons.map(({ concept }) => <span key={concept}>{reasonLabel(concept, student)}</span>)}
      </span>
      {student.silent ? <span className="silent-tag">Đã im</span> : <span />}
    </li>
  )
})

export function DecisionChapter({ runId, offerings, visible }: { runId: number; offerings: Offering[]; visible: boolean }) {
  const report = useContext(StatusContext)
  const served = useMemo(() => offerings.filter((row) => row.code_presentation.startsWith('2014')), [offerings])
  const [offeringKey, setOfferingKey] = useState(
    () => (served.find((row) => row.code_module === 'FFF' && row.code_presentation === '2014J') ?? served[0])?.offering_key,
  )
  const [week, setWeek] = useState(7)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [contacts, setContacts] = useState(0)
  const [efficacy, setEfficacy] = useState(0.2)
  const [drawer, setDrawer] = useState<'evaluation' | 'model' | null>(null)
  const cohort = useRef(0)

  const offering = served.find((row) => row.offering_key === offeringKey)
  const selectionKey = `${offeringKey}-${week}`

  useEffect(() => {
    if (!offering || !visible) return
    const selection: Selection = { module: offering.code_module, presentation: offering.code_presentation, week }
    const controller = new AbortController()
    Promise.all([fetchStudents(selection, runId, controller.signal), fetchCurve(selection, runId, controller.signal)])
      .then(([students, curve]) => {
        // Captured here: the updater runs during render, after the ref below has moved on.
        const previousCohort = cohort.current
        setContacts((current) => rescaleContacts(current, previousCohort, curve.enrolled))
        cohort.current = curve.enrolled
        setLoaded({ key: selectionKey, students, curve })
        setError(null)
        report({ code: null, message: null, elapsed: null })
      })
      .catch((reason: Error) => {
        if (reason.name === 'AbortError') return
        const failure = reason instanceof ApiError ? reason : new ApiError('connection', 'Không gọi được API.')
        // Figures from the previous selection must not stay under the new one.
        setLoaded(null)
        setError(failure)
        report({ code: failure.code, message: failure.message, elapsed: null })
      })
    return () => controller.abort()
  }, [offering, week, runId, selectionKey, attempt, visible, report])

  const curve = loaded?.curve
  const students = loaded?.students.students ?? []
  const modelTp = curve?.tp_model[contacts] ?? 0
  const baselineTp = curve?.tp_baseline[contacts] ?? 0
  const selected = useMemo(() => students.slice(0, contacts), [students, contacts])

  if (!visible) return null
  return (
    <main className="chapter">
      <div className="toolbar">
        <label>
          <span className="sr-only">Lần mở</span>
          <select value={offeringKey} onChange={(event) => setOfferingKey(Number(event.target.value))}>
            {served.map((row) => (
              <option key={row.offering_key} value={row.offering_key}>{row.code_module} · {row.code_presentation}</option>
            ))}
          </select>
        </label>
        <div className="segmented" role="group" aria-label="Tuần">
          {WEEKS.map((value) => (
            <button key={value} aria-pressed={week === value} onClick={() => setWeek(value)}>Tuần {value}</button>
          ))}
        </div>
        {curve && (
          <span className="muted">
            {formatCount(curve.enrolled)} còn học · {formatCount(curve.leavers.left_before_cutoff)} đã hủy, trong đó {formatCount(curve.leavers.left_before_first_cutoff)} đến ngày 6
            <Info>Danh sách chỉ gồm lượt còn trong snapshot. Lượt hủy đến ngày 6 chưa có hành vi học nên không dự báo được; báo cáo riêng, không tính vào đường cong.</Info>
          </span>
        )}
        <span className="toolbar-end">
          <button className="link" onClick={() => setDrawer('model')}>Mô hình</button>
          <button className="link" onClick={() => setDrawer('evaluation')}>Đánh giá</button>
        </span>
      </div>

      {error && <LoadError error={error} retry={() => setAttempt((value) => value + 1)} />}

      <div className="stage">
        <div className="sky">
          {curve && (
            <>
              <GainCurve curve={curve} contacts={contacts} maxContacts={maxContacts(curve.enrolled)} onSelect={setContacts} />
              <ul className="legend">
                <li><i className="swatch model" /> Mô hình</li>
                <li><i className="swatch baseline" /> {BASELINE_LABELS[curve.baseline]}</li>
                <li><i className="swatch random" /> Ngẫu nhiên</li>
                <li className="muted">Hồi cứu trên kết quả thật<Info>Kết quả thật chỉ dùng để vẽ đường cong tổng hợp, không dùng để xếp hạng. Đường baseline thẳng đoạn dài vì nhiều sinh viên đồng giá trị; tie chia theo kỳ vọng.</Info></li>
              </ul>
            </>
          )}
        </div>

        <section className="panel" aria-label="Danh sách liên hệ" aria-busy={loaded?.key !== selectionKey}>
          <label className="budget">
            <span className="muted">Tuần này liên hệ</span>
            <output>{formatCount(contacts)}</output>
            <input type="range" min={1} max={curve ? maxContacts(curve.enrolled) : 1} value={contacts}
              onChange={(event) => setContacts(Number(event.target.value))} aria-label="Số lượt liên hệ" />
          </label>

          {curve && (
            <>
              <div className="impact">
                <div>
                  <span className="muted">Trúng nhóm nguy cơ<Info>Hồi cứu trên kết quả thật của lần mở này.</Info></span>
                  <b>{formatDecimal(modelTp)}</b>
                </div>
                <div>
                  <span className="muted">{BASELINE_LABELS[curve.baseline]}<Info>Baseline một đặc trưng, chốt từ dữ liệu 2013.</Info></span>
                  <b className="quiet">{formatDecimal(baselineTp)}</b>
                </div>
              </div>
              <div className="assumption">
                <div className="assumption-head">
                  <span className="tag">Giả định</span>
                  <span className="muted">Hiệu quả can thiệp {Math.round(efficacy * 100)}%<Info>Dữ liệu không đo được hiệu quả can thiệp. Tác động = (trúng của mô hình − trúng của baseline) × hiệu quả giả định. Đây là ước tính có điều kiện, không phải kết quả.</Info></span>
                </div>
                <input type="range" min={0.05} max={0.5} step={0.05} value={efficacy}
                  onChange={(event) => setEfficacy(Number(event.target.value))} aria-label="Hiệu quả giả định" />
                <table className="sensitivity">
                  <thead>
                    <tr>
                      <th scope="row">Nếu hiệu quả</th>
                      {EFFICACY_LEVELS.map((level) => <th scope="col" key={level}>{level * 100}%</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <th scope="row">Giữ thêm</th>
                      {EFFICACY_LEVELS.map((level) => {
                        const value = estimatedImpact(modelTp, baselineTp, level)
                        return <td key={level}>{value > 0 ? '+' : ''}{formatDecimal(value)}</td>
                      })}
                    </tr>
                  </tbody>
                </table>
                <span className="muted">Với {Math.round(efficacy * 100)}%: <b className="current">{modelTp > baselineTp ? '+' : ''}{formatDecimal(estimatedImpact(modelTp, baselineTp, efficacy))}</b> sinh viên so với baseline</span>
              </div>
            </>
          )}

          <ol className="contacts">
            {selected.map((student) => <ContactRow key={student.id_student} student={student} />)}
          </ol>
        </section>
      </div>

      {drawer === 'evaluation' && <EvaluationPanel onClose={() => setDrawer(null)} />}
      {drawer === 'model' && <ModelPanel onClose={() => setDrawer(null)} />}
    </main>
  )
}
