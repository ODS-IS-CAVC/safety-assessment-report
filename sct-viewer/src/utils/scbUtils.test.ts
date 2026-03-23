import { describe, it, expect } from 'vitest'
import SAT from 'sat'
import {
  createVehicleOBBPolygon,
  createSCBPolygon,
  createIncrementalSCBPolygon,
  checkSCBCollisionsWithPolygons,
  calculateEgoStrokeStyles,
  calculateTargetStrokeStyles,
} from './scbUtils'

describe('createVehicleOBBPolygon', () => {
  it('heading=0で正しい矩形を生成する', () => {
    const poly = createVehicleOBBPolygon(0, 0, 0, 4, 2, 1.5)
    expect(poly).toBeInstanceOf(SAT.Polygon)
    // 4頂点が存在すること
    expect(poly.calcPoints.length).toBe(4)
  })

  it('headingを回転させても4頂点が生成される', () => {
    const poly = createVehicleOBBPolygon(10, 20, Math.PI / 2, 4, 2, 1.5)
    expect(poly.calcPoints.length).toBe(4)
  })
})

describe('createSCBPolygon', () => {
  it('scbValue=0の場合nullを返す', () => {
    const result = createSCBPolygon(0, 0, 0, 4, 2, 1.5, 0, 'forward')
    expect(result).toBeNull()
  })

  it('scbValue>0で正しいポリゴンを返す', () => {
    const poly = createSCBPolygon(0, 0, 0, 4, 2, 1.5, 5.0, 'forward')
    expect(poly).not.toBeNull()
    expect(poly!.calcPoints.length).toBe(4)
  })

  it('全4方向で有効なポリゴンを生成する', () => {
    const directions = ['forward', 'backward', 'left', 'right'] as const
    for (const dir of directions) {
      const poly = createSCBPolygon(0, 0, 0, 4, 2, 1.5, 3.0, dir)
      expect(poly).not.toBeNull()
      expect(poly!.calcPoints.length).toBe(4)
    }
  })
})

describe('createIncrementalSCBPolygon', () => {
  it('endOffset <= startOffsetの場合nullを返す', () => {
    const result = createIncrementalSCBPolygon(0, 0, 0, 4, 2, 1.5, 5.0, 3.0, 'forward', false)
    expect(result).toBeNull()
  })

  it('有効な増分範囲でポリゴンを返す', () => {
    const poly = createIncrementalSCBPolygon(0, 0, 0, 4, 2, 1.5, 3.0, 5.0, 'forward', false)
    expect(poly).not.toBeNull()
    expect(poly!.calcPoints.length).toBe(4)
  })

  it('衝突判定モードでもポリゴンを返す', () => {
    const poly = createIncrementalSCBPolygon(0, 0, 0, 4, 2, 1.5, 3.0, 5.0, 'forward', true)
    expect(poly).not.toBeNull()
  })
})

describe('checkSCBCollisionsWithPolygons', () => {
  const makePolygons = (x: number) => {
    const body = createVehicleOBBPolygon(x, 0, 0, 4, 2, 1.5)
    const scb0 = createSCBPolygon(x, 0, 0, 4, 2, 1.5, 2.0, 'forward')
    const scb1 = createSCBPolygon(x, 0, 0, 4, 2, 1.5, 4.0, 'forward')
    const scb2 = createSCBPolygon(x, 0, 0, 4, 2, 1.5, 6.0, 'forward')
    const scb3 = createSCBPolygon(x, 0, 0, 4, 2, 1.5, 8.0, 'forward')
    return { body, scb0, scb1, scb2, scb3 }
  }

  it('遠く離れた車両は安全(level=4)', () => {
    const ego = makePolygons(0)
    const target = makePolygons(100)
    const result = checkSCBCollisionsWithPolygons(ego, target)
    expect(result.level).toBe(4)
    expect(result.message).toBe('安全')
  })

  it('車両本体が重なっている場合はlevel=-1', () => {
    const ego = makePolygons(0)
    const target = makePolygons(2) // 近接
    const result = checkSCBCollisionsWithPolygons(ego, target)
    expect(result.level).toBe(-1)
  })
})

describe('calculateEgoStrokeStyles', () => {
  it('overlapLevel=4の場合すべての枠線幅が0', () => {
    const styles = calculateEgoStrokeStyles(4, undefined)
    expect(styles.strokeWidth0).toBe(0)
    expect(styles.strokeWidth1).toBe(0)
    expect(styles.strokeWidth2).toBe(0)
    expect(styles.strokeWidth3).toBe(0)
  })

  it('undefinedの場合すべての枠線幅が0', () => {
    const styles = calculateEgoStrokeStyles(undefined, undefined)
    expect(styles.strokeWidth0).toBe(0)
    expect(styles.strokeWidth1).toBe(0)
  })

  it('overlapLevel<=0の場合すべてのSCBが枠線あり', () => {
    const mockResult = {
      level: 0,
      message: '⚠️ 極めて危険（SD重複）',
      hasBigOBBOverlap: false,
      overlappedSCB: null as 'scb1' | 'scb2' | 'scb3' | null,
      egoSCB1_vs_targetSCB: { scb1: false, scb2: false, scb3: false },
      egoSCB2_vs_targetSCB: { scb1: false, scb2: false, scb3: false },
      egoSCB3_vs_targetSCB: { scb1: false, scb2: false, scb3: false },
      targetSCB1_vs_egoSCB: { scb1: false, scb2: false, scb3: false },
      targetSCB2_vs_egoSCB: { scb1: false, scb2: false, scb3: false },
      targetSCB3_vs_egoSCB: { scb1: false, scb2: false, scb3: false },
    }
    const styles = calculateEgoStrokeStyles(0, mockResult)
    expect(styles.strokeWidth0).toBe(3)
    expect(styles.strokeWidth1).toBe(3)
    expect(styles.strokeWidth2).toBe(3)
    expect(styles.strokeWidth3).toBe(3)
  })
})

describe('calculateTargetStrokeStyles', () => {
  it('overlapLevel=4の場合すべての枠線幅が0', () => {
    const styles = calculateTargetStrokeStyles(4, undefined)
    expect(styles.strokeWidth0).toBe(0)
    expect(styles.strokeWidth1).toBe(0)
  })
})
