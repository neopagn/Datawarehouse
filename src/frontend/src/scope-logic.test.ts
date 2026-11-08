import { describe, expect, it } from 'vitest'
import type { Offering } from './api'
import {
  cleanPhase, deepestLevel, examScoreComparable, filterOptions, lastWeek, levelAllowed, reachableWeek,
  selectedOfferings, WHOLE_WAREHOUSE, withDomain, withModule, withPresentation,
} from './scope-logic'

const row = (key: number, domain: string, module: string, presentation: string, length_weeks = 38): Offering => ({
  offering_key: key, domain, code_module: module, code_presentation: presentation, length_weeks,
})
const OFFERINGS = [
  row(1, 'STEM', 'CCC', '2014B', 35), row(2, 'STEM', 'CCC', '2014J', 38), row(3, 'STEM', 'FFF', '2013J', 39),
  row(4, 'Social Sciences', 'AAA', '2013J', 38), row(5, 'Social Sciences', 'DDD', '2013B', 5),
]

describe('filter cascade', () => {
  it('limits children to the chosen parent', () => {
    expect(filterOptions(OFFERINGS, 'code_module', { domain: 'STEM' })).toEqual(['CCC', 'FFF'])
    expect(filterOptions(OFFERINGS, 'code_presentation', { module: 'CCC' })).toEqual(['2014B', '2014J'])
  })

  it('resets children when a parent changes', () => {
    const chosen = withPresentation(withModule(OFFERINGS, WHOLE_WAREHOUSE, 'CCC'), '2014J')
    expect(chosen).toEqual({ domain: 'STEM', module: 'CCC', presentation: '2014J' })
    expect(withModule(OFFERINGS, chosen, 'FFF').presentation).toBeNull()
    expect(withDomain('Social Sciences')).toEqual({ domain: 'Social Sciences', module: null, presentation: null })
  })

  it('keeps the domain when the module is cleared', () => {
    expect(withModule(OFFERINGS, { domain: 'STEM', module: 'CCC', presentation: null }, null).domain).toBe('STEM')
  })

  it('selects by every set level', () => {
    expect(selectedOfferings(OFFERINGS, WHOLE_WAREHOUSE)).toHaveLength(5)
    expect(selectedOfferings(OFFERINGS, { domain: 'STEM', module: 'CCC', presentation: '2014J' })).toEqual([OFFERINGS[1]])
  })
})

describe('weeks', () => {
  it('stops at the longest selected offering', () => {
    expect(lastWeek(OFFERINGS)).toBe(38)
    expect(lastWeek([OFFERINGS[0]!])).toBe(34)
  })

  it('keeps a reachable week and resets an unreachable one', () => {
    expect(reachableWeek(30, [OFFERINGS[0]!])).toBe(30)
    expect(reachableWeek(36, [OFFERINGS[0]!])).toBe(7)
    expect(reachableWeek(36, [OFFERINGS[4]!])).toBe(0)
  })
})

describe('comparison rules', () => {
  it('offers the presentation level only inside one module', () => {
    expect(levelAllowed('presentation', WHOLE_WAREHOUSE)).toBe(false)
    expect(levelAllowed('presentation', { domain: 'STEM', module: 'CCC', presentation: null })).toBe(true)
    expect(deepestLevel({ domain: 'STEM', module: null, presentation: null })).toBe('module')
    expect(deepestLevel({ domain: 'STEM', module: 'CCC', presentation: null })).toBe('presentation')
  })

  it('shows Exam scores only when every selected offering records them', () => {
    expect(examScoreComparable(OFFERINGS.slice(0, 2))).toBe(true)
    expect(examScoreComparable([OFFERINGS[4]!])).toBe(true)
    expect(examScoreComparable(OFFERINGS)).toBe(false)
    expect(examScoreComparable([])).toBe(false)
  })
})

describe('labels', () => {
  it('removes the sort prefix', () => expect(cleanPhase('3. Ngày 1–27')).toBe('Ngày 1–27'))
})
