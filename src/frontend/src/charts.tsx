import { line, scaleLinear } from 'd3'
import { useEffect, useMemo, useRef, useState } from 'react'
import { formatCount, formatDecimal, separateLabels } from './decision-logic'

export function useSize<T extends HTMLElement>() {
  const box = useRef<T>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    if (box.current) observer.observe(box.current)
    return () => observer.disconnect()
  }, [])
  return { box, size }
}

export const referenceLine = (value: number | null, label: string) => (value === null ? null : { value, label })

export interface BarRow {
  key: string
  label: string
  value: number | null
  note?: string
  onClick?: () => void
}

/** Rows carry their exact value and group size, so the chart doubles as its table view. */
export function HBars({ rows, unit = '', max, reference }: {
  rows: BarRow[]
  unit?: string
  max?: number
  reference?: { value: number; label: string } | null
}) {
  const top = max ?? Math.max(...rows.map((row) => row.value ?? 0), reference?.value ?? 0, 1) * 1.08
  return (
    <div className="hbars">
      {reference && (
        <div className="reference-label"><i style={{ left: `${(reference.value / top) * 100}%` }}><span>{reference.label} {formatDecimal(reference.value)}{unit}</span></i></div>
      )}
      {rows.map((row) => {
        const above = !reference || (row.value ?? 0) >= reference.value
        const content = (
          <>
            <span className="bar-label">{row.label}{row.onClick && <em> ›</em>}</span>
            <span className="bar-track">
              {row.value !== null && <i className={above ? 'bar lit' : 'bar'} style={{ width: `${(row.value / top) * 100}%` }} />}
              {reference && <i className="bar-reference" style={{ left: `${(reference.value / top) * 100}%` }} />}
            </span>
            <span className="bar-value">{row.value === null ? '—' : `${formatDecimal(row.value)}${unit}`}</span>
            <span className="bar-note">{row.note}</span>
          </>
        )
        return row.onClick
          ? <button key={row.key} className="bar-row" onClick={row.onClick}>{content}</button>
          : <div key={row.key} className="bar-row">{content}</div>
      })}
    </div>
  )
}

export interface Series {
  key: string
  label: string
  color: string
  points: { x: number; y: number }[]
  dashed?: boolean
}

const MARGIN = { top: 14, right: 110, bottom: 44, left: 56 }

/** Lines share one axis, each named at its end; `onPick` lets a click on the plot choose an x value. */
export function LineChart({ series, xLabel, yLabel, cursor, onPick, dots, yMax }: {
  series: Series[]
  xLabel: string
  yLabel: string
  cursor?: number
  onPick?: (x: number) => void
  dots?: boolean
  yMax?: number
}) {
  const { box, size } = useSize<HTMLDivElement>()
  const [hovered, setHovered] = useState<number | null>(null)
  const xs = useMemo(() => [...new Set(series.flatMap((item) => item.points.map((point) => point.x)))].sort((a, b) => a - b), [series])
  const plotWidth = Math.max(size.width - MARGIN.left - MARGIN.right, 0)
  const plotHeight = Math.max(size.height - MARGIN.top - MARGIN.bottom, 0)
  const bottom = MARGIN.top + plotHeight
  const x = scaleLinear([xs[0] ?? 0, xs[xs.length - 1] ?? 1], [MARGIN.left, MARGIN.left + plotWidth])
  const top = yMax ?? Math.max(...series.flatMap((item) => item.points.map((point) => point.y)), 1) * 1.05
  const y = scaleLinear([0, top], [bottom, MARGIN.top]).nice()
  const path = line<{ x: number; y: number }>((point) => x(point.x), (point) => y(point.y))
  const labelled = series.filter((item) => item.points.length > 0)
  const ends = separateLabels(labelled.map((item) => y(item.points[item.points.length - 1]!.y)), 17)

  function nearest(event: React.PointerEvent | React.MouseEvent) {
    const left = box.current?.getBoundingClientRect().left ?? 0
    const target = x.invert(event.clientX - left)
    return xs.reduce((best, value) => (Math.abs(value - target) < Math.abs(best - target) ? value : best), xs[0] ?? 0)
  }

  const ready = plotWidth > 0 && plotHeight > 0 && xs.length > 0
  return (
    <div className="line-chart" ref={box}>
      {ready && (
        <svg width={size.width} height={size.height} role="img" aria-label={`${yLabel} theo ${xLabel}`}>
          {y.ticks(5).map((tick) => (
            <g key={tick}>
              <line className="grid" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} />
              <text className="tick" x={MARGIN.left - 10} y={y(tick)} textAnchor="end" dominantBaseline="middle">{formatCount(tick)}</text>
            </g>
          ))}
          {x.ticks(8).map((tick) => (
            <text key={tick} className="tick" x={x(tick)} y={bottom + 18} textAnchor="middle">{formatCount(tick)}</text>
          ))}
          <text className="tick" x={MARGIN.left + plotWidth / 2} y={size.height - 6} textAnchor="middle">{xLabel}</text>
          <text className="tick" transform={`translate(14 ${MARGIN.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
          {cursor !== undefined && cursor >= (xs[0] ?? 0) && cursor <= (xs[xs.length - 1] ?? 0) && (
            <line className="cursor" x1={x(cursor)} x2={x(cursor)} y1={MARGIN.top} y2={bottom} />
          )}
          {series.map((item) => (
            <path key={item.key} className="series" d={path(item.points) ?? ''} stroke={item.color}
              strokeDasharray={item.dashed ? '5 5' : undefined} />
          ))}
          {dots && series.map((item) => item.points.map((point) => (
            <circle key={`${item.key}-${point.x}`} className="point" cx={x(point.x)} cy={y(point.y)} r={4.5} fill={item.color} />
          )))}
          {labelled.map((item, index) => (
            <text key={item.key} className="end-label" x={MARGIN.left + plotWidth + 10} y={ends[index]} dominantBaseline="middle">{item.label}</text>
          ))}
          {hovered !== null && <line className="crosshair" x1={x(hovered)} x2={x(hovered)} y1={MARGIN.top} y2={bottom} />}
          <rect className={onPick ? 'hit pick' : 'hit'} x={MARGIN.left} y={MARGIN.top} width={plotWidth} height={plotHeight}
            onPointerMove={(event) => setHovered(nearest(event))} onPointerLeave={() => setHovered(null)}
            onClick={(event) => onPick?.(nearest(event))} />
        </svg>
      )}
      {ready && hovered !== null && (
        <div className="tooltip" style={{ left: Math.min(x(hovered), size.width - 200), top: MARGIN.top + 6, transform: 'translateX(12px)' }}>
          <strong>{xLabel} {formatDecimal(hovered)}</strong>
          {series.map((item) => {
            const point = item.points.find((candidate) => candidate.x === hovered)
            return point ? <span key={item.key}>{item.label}: {formatDecimal(point.y)}</span> : null
          })}
        </div>
      )}
    </div>
  )
}
