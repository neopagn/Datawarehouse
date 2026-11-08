import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, fetchMeta, type Meta } from './api'
import { DecisionChapter } from './decision-chapter'
import { formatDecimal } from './decision-logic'
import { WHOLE_WAREHOUSE, type Scope } from './scope-logic'
import { SignalsChapter } from './signals-chapter'
import { SituationChapter } from './situation-chapter'
import { LoadError } from './ui-parts'
import { StatusContext, type WarehouseStatus } from './use-screen'

const CHAPTERS = ['Tình hình', 'Tín hiệu', 'Quyết định']

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [metaError, setMetaError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [chapter, setChapter] = useState(0)
  const [scope, setScope] = useState<Scope>(WHOLE_WAREHOUSE)
  const [status, setStatus] = useState<WarehouseStatus>({ code: null, message: null, elapsed: null })
  const report = useCallback((next: WarehouseStatus) => setStatus(next), [])

  useEffect(() => {
    const controller = new AbortController()
    fetchMeta(controller.signal)
      .then((next) => {
        setMeta(next)
        setMetaError(null)
      })
      .catch((reason: Error) => {
        if (reason.name === 'AbortError') return
        setMeta(null)
        setMetaError(reason instanceof ApiError ? reason : new ApiError('connection', 'Không gọi được API.'))
      })
    return () => controller.abort()
  }, [attempt])

  const failure = metaError?.code ?? status.code
  const shared = useMemo(() => meta && { offerings: meta.offerings, runId: meta.run_id, scope, onScope: setScope }, [meta, scope])

  return (
    <StatusContext.Provider value={report}>
      <nav className="chapters" aria-label="Chương">
        <span className="brand">OULAD</span>
        {CHAPTERS.map((name, index) => (
          <button key={name} aria-current={chapter === index ? 'page' : undefined} onClick={() => setChapter(index)}>
            <span className="chapter-number">{index + 1}</span>{name}
          </button>
        ))}
        <span className={failure ? 'warehouse down' : 'warehouse'} role="status">
          {failure
            ? <>▲ Kho không sẵn sàng · {failure}</>
            : meta && <>● Kho sẵn sàng · ETL SUCCESS · run {meta.run_id}{status.elapsed !== null && ` · ${formatDecimal(status.elapsed * 1000)} ms`}</>}
        </span>
      </nav>
      {metaError && <LoadError error={metaError} retry={() => setAttempt((value) => value + 1)} />}
      {shared && chapter === 0 && <SituationChapter {...shared} />}
      {shared && chapter === 1 && <SignalsChapter {...shared} />}
      {meta && <DecisionChapter runId={meta.run_id} offerings={meta.offerings} visible={chapter === 2} />}
    </StatusContext.Provider>
  )
}
