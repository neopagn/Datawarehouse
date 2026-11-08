import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { ApiError, Offering } from './api'
import { filterOptions, lastWeek, selectedOfferings, withDomain, withModule, withPresentation, type Scope } from './scope-logic'

/** Details that work on video too: a click opens them, unlike a title attribute. */
export function Info({ children, label = 'Chi tiết' }: { children: ReactNode; label?: string }) {
  const button = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<{ left: number; top?: number; bottom?: number } | null>(null)

  useEffect(() => {
    if (!position) return
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape'
        : !panel.current?.contains(event.target as Node) && !button.current?.contains(event.target as Node)) setPosition(null)
    }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', close)
    }
  }, [position])

  function toggle(event: React.MouseEvent) {
    event.preventDefault()
    const rect = button.current?.getBoundingClientRect()
    if (!rect || position) return setPosition(null)
    const left = Math.max(12, Math.min(rect.left - 12, window.innerWidth - 372))
    const upward = rect.bottom > window.innerHeight * 0.7
    setPosition(upward ? { left, bottom: window.innerHeight - rect.top + 6 } : { left, top: rect.bottom + 6 })
  }

  return (
    <>
      <button ref={button} className="info" onClick={toggle} aria-label={label} aria-expanded={position !== null}>ⓘ</button>
      {position && <div ref={panel} className="info-panel" role="note" style={position}>{children}</div>}
    </>
  )
}

export function Segmented<T extends string>({ label, options, value, onChange }: {
  label: string
  options: { key: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.key} aria-pressed={value === option.key} onClick={() => onChange(option.key)}>{option.label}</button>
      ))}
    </div>
  )
}

export function Loading() {
  return <div className="view loading" aria-busy="true"><span className="muted">Đang tải từ kho…</span></div>
}

export function LoadError({ error, retry }: { error: ApiError; retry: () => void }) {
  const stale = error.code === 'stale_run' || error.code === 'stale_model'
  return (
    <div className="load-error" role="alert">
      <b>▲ {error.code}</b>
      <span>{error.message}</span>
      <button onClick={() => (stale ? window.location.reload() : retry())}>{stale ? 'Tải lại trang' : 'Thử lại'}</button>
    </div>
  )
}

function FilterSelect({ label, value, options, onChange }: {
  label: string
  value: string | null
  options: string[]
  onChange: (value: string | null) => void
}) {
  return (
    <label className="filter">
      <span>{label}</span>
      <select value={value ?? ''} onChange={(event) => onChange(event.target.value || null)}>
        <option value="">Tất cả</option>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  )
}

export function ScopeFilters({ offerings, scope, onChange }: { offerings: Offering[]; scope: Scope; onChange: (scope: Scope) => void }) {
  return (
    <>
      <FilterSelect label="Lĩnh vực" value={scope.domain} options={filterOptions(offerings, 'domain')}
        onChange={(value) => onChange(withDomain(value))} />
      <FilterSelect label="Module" value={scope.module} options={filterOptions(offerings, 'code_module', scope)}
        onChange={(value) => onChange(withModule(offerings, scope, value))} />
      {/* Presentations are compared only inside a module, so this filter appears once one is chosen. */}
      {scope.module && (
        <FilterSelect label="Lần mở" value={scope.presentation}
          options={filterOptions(offerings, 'code_presentation', scope)}
          onChange={(value) => onChange(withPresentation(scope, value))} />
      )}
    </>
  )
}

export function WeekControl({ offerings, scope, week, onChange, coverage }: {
  offerings: Offering[]
  scope: Scope
  week: number
  onChange: (week: number) => void
  coverage: { covered: number | null; selected: number } | null
}) {
  return (
    <label className="week">
      <span>Tuần <b>{week}</b> · ngày {7 * week}–{7 * week + 6}{coverage && coverage.covered !== null ? ` · ${coverage.covered}/${coverage.selected} lần mở` : ''}</span>
      <input type="range" min={0} max={lastWeek(selectedOfferings(offerings, scope))} value={week}
        onChange={(event) => onChange(Number(event.target.value))} aria-label="Tuần" />
    </label>
  )
}

export function Stat({ label, value, info }: { label: string; value: string; info?: ReactNode }) {
  return (
    <div className="stat">
      <span className="muted">{label}{info && <Info>{info}</Info>}</span>
      <b>{value}</b>
    </div>
  )
}
