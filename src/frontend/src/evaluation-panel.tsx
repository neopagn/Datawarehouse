import { useEffect, useMemo, useState } from 'react'
import { fetchEvaluation, type Evaluation, type Precision, type WeekEvaluation } from './api'
import { LineChart, type Series } from './charts'
import { BASELINE_LABELS, formatCount, formatPercent, offeringsWon, SHARES } from './decision-logic'
import { Segmented } from './ui-parts'

type Tab = 'precision' | 'offerings' | 'calibration' | 'sensitivity'

const TABS: { key: Tab; label: string }[] = [
  { key: 'precision', label: 'Precision' },
  { key: 'offerings', label: 'Theo lần mở' },
  { key: 'calibration', label: 'Calibration' },
  { key: 'sensitivity', label: 'Độ nhạy' },
]
const GROUPS = ['2014B', '2014J', 'CCC']
const METHODS = ['model', 'missed', 'silence', 'clicks'] as const
const SENSITIVITIES = [
  ['no_score_lag', 'Bỏ trễ điểm 2 tuần'],
  ['without_repeat_students', 'Bỏ sinh viên học lại'],
  ['train_2013b_test_2014b', 'Train 2013B, test 2014B'],
] as const
const FOOTERS: Record<Tab, string> = {
  precision: 'Trung bình theo lần mở. Chốt mô hình trên 2013. 2014J là tập kiểm tra sạch; CCC không có trong 2013.',
  offerings: 'Dòng đậm: mô hình không thua baseline nào. Chỉ so các lần mở trong cùng module.',
  calibration: 'Mỗi điểm là một decile. Xác suất nhóm cao bị thổi phồng ở tuần 7 và 11, không hiệu chỉnh trên 2014, nên giao diện chỉ dùng thứ hạng.',
  sensitivity: 'Ngoài CCC, trung bình theo lần mở. Dòng đậm: mô hình không thua baseline nào. Train 2013B chỉ trên BBB, DDD, FFF.',
}

const methodLabel = (method: (typeof METHODS)[number]) => (method === 'model' ? 'Mô hình' : BASELINE_LABELS[method])
const wins = (precision: Precision, share: string) =>
  (['missed', 'silence', 'clicks'] as const).every((name) => (precision.model[share] ?? 0) >= (precision[name][share] ?? 0))

export function EvaluationPanel({ onClose }: { onClose: () => void }) {
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('precision')
  const [share, setShare] = useState<string>('10')
  const [week, setWeek] = useState('7')
  const [withoutSilent, setWithoutSilent] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetchEvaluation(controller.signal).then(setEvaluation).catch((reason: Error) => {
      if (reason.name !== 'AbortError') setError(reason.message)
    })
    return () => controller.abort()
  }, [])

  const current = evaluation?.weeks[week]
  const weeks = Object.keys(evaluation?.weeks ?? {}).map((key) => ({ key, label: `Tuần ${key}` }))
  const shares = SHARES.map((value) => ({ key: value as string, label: `Top ${value}%` }))

  return (
    <aside className="evaluation" role="dialog" aria-label="Đánh giá mô hình trên 2014">
      <header>
        <h2>Đánh giá trên 2014</h2>
        <button className="close" onClick={onClose} aria-label="Đóng">×</button>
      </header>
      <Segmented label="Nội dung" options={TABS} value={tab} onChange={setTab} />
      <div className="controls">
        {tab !== 'calibration' && <Segmented label="Tỉ lệ liên hệ" options={shares} value={share} onChange={setShare} />}
        {(tab === 'offerings' || tab === 'calibration') && <Segmented label="Tuần" options={weeks} value={week} onChange={setWeek} />}
        {(tab === 'precision' || tab === 'offerings') && (
          <label className="check">
            <input type="checkbox" checked={withoutSilent} onChange={(event) => setWithoutSilent(event.target.checked)} />
            Bỏ nhóm đã im
          </label>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {evaluation && tab === 'precision' && Object.entries(evaluation.weeks).map(([key, result]) => (
        <PrecisionTable key={key} week={key} result={result} share={share} withoutSilent={withoutSilent} />
      ))}
      {current && tab === 'offerings' && <OfferingsTable result={current} share={share} withoutSilent={withoutSilent} />}
      {current && tab === 'calibration' && <Calibration result={current} />}
      {evaluation && tab === 'sensitivity' && Object.entries(evaluation.weeks).map(([key, result]) => (
        <SensitivityTable key={key} week={key} result={result} share={share} />
      ))}
      <footer>{FOOTERS[tab]}</footer>
    </aside>
  )
}

function PrecisionTable({ week, result, share, withoutSilent }: { week: string; result: WeekEvaluation; share: string; withoutSilent: boolean }) {
  return (
    <section>
      <h3>
        Tuần {week}
        {!withoutSilent && <span>Mô hình ≥ mọi baseline: {offeringsWon(Object.values(result.offerings), share)}/{Object.keys(result.offerings).length} lần mở</span>}
      </h3>
      <table>
        <thead><tr><th scope="col">Precision</th>{GROUPS.map((group) => <th scope="col" key={group}>{group}</th>)}</tr></thead>
        <tbody>
          {METHODS.map((method) => (
            <tr key={method} className={method === 'model' ? 'model' : undefined}>
              <th scope="row">{methodLabel(method)}{method === result.frozen_baseline && <em> · chốt từ 2013</em>}</th>
              {GROUPS.map((group) => {
                const data = result.groups[group]
                const table = withoutSilent ? data?.precision_without_silent : data?.precision
                return <td key={group}>{formatPercent(table?.[method][share] ?? NaN)}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function OfferingsTable({ result, share, withoutSilent }: { result: WeekEvaluation; share: string; withoutSilent: boolean }) {
  return (
    <table className="compact">
      <thead>
        <tr><th scope="col">Lần mở</th><th scope="col">Lượt</th><th scope="col">Nền</th>{METHODS.map((method) => <th scope="col" key={method}>{methodLabel(method)}</th>)}</tr>
      </thead>
      <tbody>
        {Object.entries(result.offerings).map(([name, row]) => {
          const table = withoutSilent ? row.precision_without_silent : row.precision
          return (
            <tr key={name} className={wins(table, share) ? 'model' : undefined}>
              <th scope="row">{name}</th><td>{formatCount(row.rows)}</td><td>{formatPercent(row.base_rate)}</td>
              {METHODS.map((method) => <td key={method}>{formatPercent(table[method][share] ?? NaN)}</td>)}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function Calibration({ result }: { result: WeekEvaluation }) {
  const series = useMemo<Series[]>(() => {
    const points = (bins: WeekEvaluation['calibration']['ccc']) => bins.map((bin) => ({ x: bin.predicted * 100, y: bin.observed * 100 }))
    return [
      { key: 'ideal', label: 'Khớp hoàn hảo', color: '#7d8799', dashed: true, points: [{ x: 0, y: 0 }, { x: 100, y: 100 }] },
      { key: 'rest', label: 'Ngoài CCC', color: '#e26b30', points: points(result.calibration.excluding_ccc) },
      { key: 'ccc', label: 'CCC', color: '#3f8ae0', points: points(result.calibration.ccc) },
    ]
  }, [result])
  return <div className="calibration"><LineChart series={series} xLabel="Dự báo (%)" yLabel="Thực tế (%)" dots yMax={100} /></div>
}

function SensitivityTable({ week, result, share }: { week: string; result: WeekEvaluation; share: string }) {
  return (
    <section>
      <h3>Tuần {week}<span>Sinh viên học lại: {formatCount(result.repeat_rows)}/{formatCount(result.test_rows)} dòng</span></h3>
      <table className="compact">
        <thead><tr><th scope="col">Kịch bản</th><th scope="col">Lượt</th>{METHODS.map((method) => <th scope="col" key={method}>{methodLabel(method)}</th>)}</tr></thead>
        <tbody>
          {SENSITIVITIES.map(([key, label]) => {
            const row = result.sensitivity[key]
            return (
              <tr key={key} className={wins(row.precision, share) ? 'model' : undefined}>
                <th scope="row">{label}</th><td>{formatCount(row.rows)}</td>
                {METHODS.map((method) => <td key={method}>{formatPercent(row.precision[method][share] ?? NaN)}</td>)}
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
