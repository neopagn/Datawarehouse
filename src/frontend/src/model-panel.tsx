import { useEffect, useState } from 'react'
import { fetchModel, type ModelDescription } from './api'
import { BASELINE_LABELS, formatCount, formatPercent } from './decision-logic'

const FEATURE_LABELS: Record<string, string> = {
  click_rank: 'Thứ hạng click lũy kế trong lần mở',
  silence: 'Số ngày im (log)',
  never_active: 'Chưa từng hoạt động',
  miss_rate: 'Tỉ lệ bài bỏ lỡ',
  no_due: 'Chưa có bài tới hạn',
  score: 'Điểm TB, trễ 2 tuần',
  no_score: 'Chưa có điểm',
}
const signed = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always' })

export function ModelPanel({ onClose }: { onClose: () => void }) {
  const [model, setModel] = useState<ModelDescription | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchModel(controller.signal).then(setModel).catch((reason: Error) => {
      if (reason.name !== 'AbortError') setError(reason.message)
    })
    return () => controller.abort()
  }, [])

  return (
    <aside className="evaluation" role="dialog" aria-label="Mô tả mô hình">
      <header>
        <h2>Mô hình</h2>
        <button className="close" onClick={onClose} aria-label="Đóng">×</button>
      </header>
      {error && <p className="error">{error}</p>}
      {model && (
        <>
          <p className="flow">
            <span><b>Huấn luyện</b>{model.train_offerings.length} lần mở 2013</span>
            <i>→</i>
            <span><b>Đóng băng</b>đặc trưng, C, baseline</span>
            <i>→</i>
            <span><b>Phục vụ</b>các lần mở {model.served_year}</span>
          </p>
          {Object.entries(model.weeks).map(([week, entry]) => (
            <section key={week}>
              <h3>
                Tuần {week}
                <span>C = {entry.c} · {formatCount(entry.rows)} dòng · baseline chốt: {BASELINE_LABELS[entry.baseline]}</span>
              </h3>
              <table>
                <thead><tr><th scope="col">Đặc trưng biết tại mốc</th><th scope="col">Hệ số</th></tr></thead>
                <tbody>
                  {Object.entries(entry.coefficients).map(([name, value]) => (
                    <tr key={name}><th scope="row">{FEATURE_LABELS[name] ?? name}</th><td>{signed.format(value)}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">CV trên 2013, precision TB top 5–30%: mô hình {formatPercent(entry.cv_precision)}, baseline {formatPercent(entry.baseline_cv_precision[entry.baseline])}</p>
            </section>
          ))}
          <footer>
            Hồi quy logistic trên đặc trưng đã chuẩn hóa, mỗi tuần mốc một mô hình. Không dùng nhân khẩu học hay module.
            Hệ số là liên hệ, không phải nguyên nhân. Toàn kho có {formatCount(model.leavers.left_before_first_cutoff)}/{formatCount(model.leavers.enrollments)} lượt hủy đến ngày 6: chưa có hành vi nên không dự báo được.
          </footer>
        </>
      )}
    </aside>
  )
}
