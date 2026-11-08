import type { Offering } from './api'

export interface Scope {
  domain: string | null
  module: string | null
  presentation: string | null
}

export const WHOLE_WAREHOUSE: Scope = { domain: null, module: null, presentation: null }

export const DEFAULT_WEEK = 7

type Field = 'domain' | 'code_module' | 'code_presentation'

/** Choices for one filter given its parents; mirrors src/dashboard/filters.py. */
export function filterOptions(offerings: Offering[], field: Field, scope: Partial<Scope> = {}) {
  const values = offerings
    .filter((row) => (!scope.domain || row.domain === scope.domain) && (!scope.module || row.code_module === scope.module))
    .map((row) => row[field])
  return [...new Set(values)].sort()
}

/** Changing a parent drops its children, so the warehouse never receives an impossible combination. */
export const withDomain = (domain: string | null): Scope => ({ domain, module: null, presentation: null })

export function withModule(offerings: Offering[], scope: Scope, module: string | null): Scope {
  const owner = offerings.find((row) => row.code_module === module)
  return { domain: owner?.domain ?? scope.domain, module, presentation: null }
}

export const withPresentation = (scope: Scope, presentation: string | null): Scope => ({ ...scope, presentation })

export function selectedOfferings(offerings: Offering[], scope: Scope) {
  return offerings.filter((row) =>
    (!scope.domain || row.domain === scope.domain)
    && (!scope.module || row.code_module === scope.module)
    && (!scope.presentation || row.code_presentation === scope.presentation))
}

/** Last valid week number: week_no starts at 0 and any selected offering may reach it. */
export function lastWeek(selected: Offering[]) {
  return Math.max(0, ...selected.map((row) => row.length_weeks)) - 1
}

/** The previous week survives a scope change unless the new scope cannot reach it. */
export function reachableWeek(week: number, selected: Offering[]) {
  const last = lastWeek(selected)
  if (week <= last) return week
  return DEFAULT_WEEK <= last ? DEFAULT_WEEK : 0
}

export type Level = 'domain' | 'module' | 'presentation'

export const LEVEL_GROUPING: Record<Level, number> = { domain: 3, module: 1, presentation: 0 }

export function deepestLevel(scope: Scope): Level {
  return scope.module ? 'presentation' : 'module'
}

/** Presentations are compared only inside one module, so that level needs a module first. */
export const levelAllowed = (level: Level, scope: Scope) => level !== 'presentation' || scope.module !== null

const EXAM_SCORED_MODULES = new Set(['CCC', 'DDD'])

/** Only CCC and DDD record Exam scores; elsewhere a missing score must not read as a comparison. */
export function examScoreComparable(selected: Offering[]) {
  return selected.length > 0 && selected.every((row) => EXAM_SCORED_MODULES.has(row.code_module))
}

/** Drops the "1. " prefix SQL uses only to sort buckets. */
export const cleanPhase = (phase: string) => phase.replace(/^\d+\.\s*/, '')
