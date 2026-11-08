import { describe, expect, it } from 'vitest'
import type { Precision, Student } from './api'
import {
  curveDomain, estimatedImpact, formatCount, formatDecimal, formatPercent, maxContacts, offeringsWon, randomReached, ratePct,
  reasonLabel, rescaleContacts, separateLabels,
} from './decision-logic'

const student: Student = {
  rank: 1, id_student: 1, risk: 0.5, silent: true, clicks_cum: 1200, days_since_last_activity: null,
  missed_cum: 2, due_cum: 3, score_lagged: null, reasons: [],
}

const precision = (model: number, best: number): Precision => ({
  model: { '10': model }, missed: { '10': 0 }, silence: { '10': best }, clicks: { '10': 0 },
})

describe('formatting', () => {
  it('uses Vietnamese separators', () => {
    expect(formatCount(26523)).toBe('26.523')
    expect(formatPercent(0.4217)).toBe('42,2%')
  })
})

describe('contact budget', () => {
  it('starts at ten percent and stays proportional', () => {
    expect(rescaleContacts(0, 0, 1794)).toBe(180)
    expect(rescaleContacts(100, 1000, 2000)).toBe(200)
  })

  it('never exceeds the evaluated range or falls below one', () => {
    expect(maxContacts(100)).toBe(30)
    expect(rescaleContacts(300, 1000, 100)).toBe(30)
    expect(rescaleContacts(1, 1000, 10)).toBe(1)
  })
})

describe('impact', () => {
  it('scales the measured difference by the assumption', () => {
    expect(estimatedImpact(150, 140, 0.2)).toBeCloseTo(2)
  })

  it('stays negative when the model loses', () => {
    expect(estimatedImpact(140, 150, 0.2)).toBeCloseTo(-2)
  })
})

describe('reasons', () => {
  it('names missing values instead of showing zero', () => {
    expect(reasonLabel('silence', student)).toBe('Chưa hoạt động')
    expect(reasonLabel('score', student)).toBe('Chưa có điểm')
  })

  it('shows raw values', () => {
    expect(reasonLabel('missed', student)).toBe('Bỏ 2/3 bài')
    expect(reasonLabel('score', { ...student, score_lagged: 41.5 })).toBe('Điểm 41,5')
  })
})

describe('offering wins', () => {
  it('counts ties for the model but not losses', () => {
    const results = [precision(0.9, 0.8), precision(0.8, 0.8), precision(0.7, 0.8)]
    expect(offeringsWon(results.map((item) => ({ precision: item })), '10')).toBe(2)
  })
})

describe('gain curve', () => {
  it('extends past the contact limit', () => {
    expect(curveDomain(1794)).toBe(718)
    expect(curveDomain(1794)).toBeGreaterThan(maxContacts(1794))
  })

  it('scales random contact by the base rate', () => {
    expect(randomReached(100, 400, 1000)).toBe(40)
    expect(randomReached(100, 0, 0)).toBe(0)
  })

  it('separates close labels and leaves distant ones alone', () => {
    expect(separateLabels([100, 105, 300], 18)).toEqual([100, 118, 300])
    expect(separateLabels([105, 100], 18)).toEqual([118, 100])
  })
})

describe('ratePct', () => {
  it('rounds once, from the counts', () => {
    expect(formatDecimal(ratePct(3011, 5644) as number)).toBe('53,3')
    expect(ratePct(1, 0)).toBeNull()
  })
})
