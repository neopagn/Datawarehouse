import { line, scaleLinear } from 'd3'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { CurvePayload } from './api'
import { BASELINE_LABELS, curveDomain, formatCount, formatDecimal, randomReached, separateLabels } from './decision-logic'

const MARGIN = { top: 16, right: 150, bottom: 48, left: 60 }

interface Props {
  curve: CurvePayload
  contacts: number
  maxContacts: number
  onSelect: (contacts: number) => void
}

/** Contacts against at-risk students reached, retrospectively. Clicking the plot sets the contact budget. */
export function GainCurve({ curve, contacts, maxContacts, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [hovered, setHovered] = useState<number | null>(null)

  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    if (box.current) observer.observe(box.current)
    return () => observer.disconnect()
  }, [])

  const domain = curveDomain(curve.enrolled)
  const random = (n: number) => randomReached(n, curve.at_risk, curve.enrolled)
  const model = (n: number) => curve.tp_model[n] ?? 0
  const baseline = (n: number) => curve.tp_baseline[n] ?? 0
  const plotWidth = Math.max(size.width - MARGIN.left - MARGIN.right, 0)
  const plotHeight = Math.max(size.height - MARGIN.top - MARGIN.bottom, 0)
  const bottom = MARGIN.top + plotHeight

  const { x, y, paths } = useMemo(() => {
    const yMax = Math.max(model(domain), baseline(domain)) * 1.05
    const x = scaleLinear([0, domain], [MARGIN.left, MARGIN.left + plotWidth])
    const y = scaleLinear([0, yMax], [MARGIN.top + plotHeight, MARGIN.top]).nice()
    const counts = Array.from({ length: domain + 1 }, (_, n) => n)
    const path = (value: (n: number) => number) => line<number>((n) => x(n), (n) => y(value(n)))(counts) ?? ''
    return { x, y, paths: { model: path(model), baseline: path(baseline), random: path(random) } }
    // The curve object identifies every value used by the line accessors.
  }, [curve, domain, plotWidth, plotHeight])

  function countAt(event: React.PointerEvent | React.MouseEvent) {
    const left = box.current?.getBoundingClientRect().left ?? 0
    return Math.round(x.invert(event.clientX - left))
  }

  const [modelLabel, baselineLabel, randomLabel] = separateLabels(
    [y(model(domain)), y(baseline(domain)), y(random(domain))], 18)
  const ready = plotWidth > 0 && plotHeight > 0
  const hoverCount = hovered === null ? null : Math.min(domain, Math.max(0, hovered))

  return (
    <div className="curve" ref={box}>
      {ready && (
        <svg width={size.width} height={size.height} role="img"
          aria-label={`Với ${contacts} lượt liên hệ, mô hình chạm ${Math.round(model(contacts))} sinh viên nguy cơ, ${BASELINE_LABELS[curve.baseline]} chạm ${Math.round(baseline(contacts))}`}>
          {y.ticks(5).map((tick) => (
            <g key={tick}>
              <line className="grid" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} />
              <text className="tick" x={MARGIN.left - 10} y={y(tick)} textAnchor="end" dominantBaseline="middle">{formatCount(tick)}</text>
            </g>
          ))}
          {x.ticks(6).map((tick) => (
            <text key={tick} className="tick" x={x(tick)} y={bottom + 18} textAnchor="middle">{formatCount(tick)}</text>
          ))}
          <text className="tick" x={MARGIN.left + plotWidth / 2} y={size.height - 6} textAnchor="middle">Số lượt liên hệ</text>
          <text className="tick" transform={`translate(14 ${MARGIN.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Sinh viên nguy cơ chạm được</text>

          <path className="line random" d={paths.random} />
          <path className="line baseline" d={paths.baseline} />
          <path className="line model" d={paths.model} />

          <text className="end-label strong" x={MARGIN.left + plotWidth + 10} y={modelLabel} dominantBaseline="middle">Mô hình</text>
          <text className="end-label" x={MARGIN.left + plotWidth + 10} y={baselineLabel} dominantBaseline="middle">{BASELINE_LABELS[curve.baseline]}</text>
          <text className="end-label" x={MARGIN.left + plotWidth + 10} y={randomLabel} dominantBaseline="middle">Ngẫu nhiên</text>

          <line className="cursor" x1={x(contacts)} x2={x(contacts)} y1={MARGIN.top} y2={bottom} />
          <circle className="marker baseline" cx={x(contacts)} cy={y(baseline(contacts))} r={5} />
          <circle className="marker model" cx={x(contacts)} cy={y(model(contacts))} r={5} />
          {hoverCount !== null && <line className="crosshair" x1={x(hoverCount)} x2={x(hoverCount)} y1={MARGIN.top} y2={bottom} />}

          <rect className="hit" x={MARGIN.left} y={MARGIN.top} width={plotWidth} height={plotHeight}
            onPointerMove={(event) => setHovered(countAt(event))} onPointerLeave={() => setHovered(null)}
            onClick={(event) => onSelect(Math.min(maxContacts, Math.max(1, countAt(event))))} />
        </svg>
      )}
      {hoverCount !== null && (
        <div className="tooltip" style={{ left: x(hoverCount), top: MARGIN.top + 8 }}>
          <strong>{formatCount(hoverCount)} lượt liên hệ</strong>
          <span>Mô hình: {formatDecimal(model(hoverCount))}</span>
          <span>{BASELINE_LABELS[curve.baseline]}: {formatDecimal(baseline(hoverCount))}</span>
          <span>Ngẫu nhiên: {formatDecimal(random(hoverCount))}</span>
        </div>
      )}
    </div>
  )
}
