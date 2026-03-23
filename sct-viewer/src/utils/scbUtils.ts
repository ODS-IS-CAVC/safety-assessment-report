import SAT from 'sat'

export interface SCBOverlapResult {
  level: number
  message: string
  hasBigOBBOverlap: boolean
  overlappedSCB: 'scb1' | 'scb2' | 'scb3' | null
  egoSCB1_vs_targetSCB: { scb1: boolean; scb2: boolean; scb3: boolean }
  egoSCB2_vs_targetSCB: { scb1: boolean; scb2: boolean; scb3: boolean }
  egoSCB3_vs_targetSCB: { scb1: boolean; scb2: boolean; scb3: boolean }
  targetSCB1_vs_egoSCB: { scb1: boolean; scb2: boolean; scb3: boolean }
  targetSCB2_vs_egoSCB: { scb1: boolean; scb2: boolean; scb3: boolean }
  targetSCB3_vs_egoSCB: { scb1: boolean; scb2: boolean; scb3: boolean }
  bigOBBInfo?: {
    targetOBB: { left: number; right: number; front: number; rear: number }
    egoOBB: { left: number; right: number; front: number; rear: number }
  }
}

/**
 * 車両OBBのポリゴンを作成（ワールド座標系）
 */
export function createVehicleOBBPolygon(
  vehicleX: number,
  vehicleY: number,
  vehicleHeading: number,
  vehicleLength: number,
  vehicleWidth: number,
  centerOffsetX: number
): SAT.Polygon {
  const cos = Math.cos(vehicleHeading)
  const sin = Math.sin(vehicleHeading)

  // 車両本体の矩形（ローカル座標）
  const halfLength = vehicleLength / 2
  const halfWidth = vehicleWidth / 2

  const corners = [
    { x: centerOffsetX - halfLength, y: -halfWidth },
    { x: centerOffsetX + halfLength, y: -halfWidth },
    { x: centerOffsetX + halfLength, y: halfWidth },
    { x: centerOffsetX - halfLength, y: halfWidth }
  ]

  // ワールド座標に変換
  const worldCorners = corners.map(corner => {
    const rotatedX = corner.x * cos - corner.y * sin
    const rotatedY = corner.x * sin + corner.y * cos
    return new SAT.Vector(vehicleX + rotatedX, vehicleY + rotatedY)
  })

  return new SAT.Polygon(new SAT.Vector(0, 0), worldCorners)
}

/**
 * SCB領域のポリゴンを作成（ワールド座標系）
 */
export function createSCBPolygon(
  vehicleX: number,
  vehicleY: number,
  vehicleHeading: number,
  vehicleLength: number,
  vehicleWidth: number,
  centerOffsetX: number,
  scbValue: number,
  direction: 'forward' | 'backward' | 'left' | 'right'
): SAT.Polygon | null {
  if (scbValue <= 0) return null

  const cos = Math.cos(vehicleHeading)
  const sin = Math.sin(vehicleHeading)

  let rectLocalX: number, rectLocalY: number, rectWidth: number, rectHeight: number

  if (direction === 'forward') {
    // 前方SCB交差判定: SCBの端（車両前端+scbValue）から車両サイズ分手前まで
    rectLocalX = centerOffsetX + vehicleLength / 2 + scbValue - vehicleLength
    rectLocalY = -vehicleWidth / 2
    rectWidth = vehicleLength
    rectHeight = vehicleWidth
  } else if (direction === 'backward') {
    // 後方SCB交差判定: SCBの端（車両後端-scbValue）から車両サイズ分
    rectLocalX = centerOffsetX - vehicleLength / 2 - scbValue
    rectLocalY = -vehicleWidth / 2
    rectWidth = vehicleLength
    rectHeight = vehicleWidth
  } else if (direction === 'left') {
    // 左SCB交差判定: SCBの端（車両左辺+scbValue）から車両幅分手前まで
    rectLocalX = centerOffsetX - vehicleLength / 2
    rectLocalY = vehicleWidth / 2 + scbValue - vehicleWidth
    rectWidth = vehicleLength
    rectHeight = vehicleWidth
  } else { // right
    // 右SCB交差判定: SCBの端（車両右辺-scbValue）から車両幅分
    rectLocalX = centerOffsetX - vehicleLength / 2
    rectLocalY = -vehicleWidth / 2 - scbValue
    rectWidth = vehicleLength
    rectHeight = vehicleWidth
  }

  // 矩形の4隅（ローカル座標）
  const corners = [
    { x: rectLocalX, y: rectLocalY },
    { x: rectLocalX + rectWidth, y: rectLocalY },
    { x: rectLocalX + rectWidth, y: rectLocalY + rectHeight },
    { x: rectLocalX, y: rectLocalY + rectHeight }
  ]

  // ワールド座標に変換
  const worldCorners = corners.map(corner => {
    const rotatedX = corner.x * cos - corner.y * sin
    const rotatedY = corner.x * sin + corner.y * cos
    return new SAT.Vector(vehicleX + rotatedX, vehicleY + rotatedY)
  })

  return new SAT.Polygon(new SAT.Vector(0, 0), worldCorners)
}

/**
 * 増分SCB領域のポリゴンを作成（ワールド座標系）
 * 表示用のSCB矩形と同じサイズのポリゴンを作成（SD→SCB1、SCB1→SCB2、SCB2→SCB3）
 *
 * @param forCollision true の場合、衝突判定用に縦方向も車両長さを考慮
 */
export function createIncrementalSCBPolygon(
  vehicleX: number,
  vehicleY: number,
  vehicleHeading: number,
  vehicleLength: number,
  vehicleWidth: number,
  centerOffsetX: number,
  startOffset: number,  // 開始オフセット（例: sdx, scb1x）
  endOffset: number,    // 終了オフセット（例: scb1x, scb2x）
  direction: 'forward' | 'backward' | 'left' | 'right',
  forCollision: boolean = false  // 衝突判定用フラグ
): SAT.Polygon | null {
  const width = endOffset - startOffset
  if (width <= 0) return null

  const cos = Math.cos(vehicleHeading)
  const sin = Math.sin(vehicleHeading)

  let rectLocalX: number, rectLocalY: number, rectWidth: number, rectHeight: number

  if (direction === 'forward') {
    // 前方SCB: startOffsetからendOffsetまでの範囲
    const offsetX = centerOffsetX + vehicleLength / 2
    rectLocalY = -vehicleWidth / 2
    if (forCollision) {
      // 衝突判定用：endOffset位置から後方にvehicleLength分
      rectLocalX = offsetX + endOffset - vehicleLength
      rectWidth = vehicleLength
      rectHeight = vehicleWidth
    } else {
      // 表示用：増分領域（startOffsetからendOffsetまでの細い帯）
      rectLocalX = offsetX + startOffset
      rectWidth = width
      rectHeight = vehicleWidth
    }
  } else if (direction === 'backward') {
    // 後方SCB: startOffsetからendOffsetまでの範囲（後方）
    const offsetX = centerOffsetX - vehicleLength / 2
    rectLocalY = -vehicleWidth / 2
    if (forCollision) {
      // 衝突判定用：endOffset位置からvehicleLength分
      rectLocalX = offsetX - endOffset
      rectWidth = vehicleLength
      rectHeight = vehicleWidth
    } else {
      // 表示用：増分領域（startOffsetからendOffsetまでの細い帯）
      rectLocalX = offsetX - endOffset
      rectWidth = width
      rectHeight = vehicleWidth
    }
  } else if (direction === 'left') {
    // 左SCB: startOffsetからendOffsetまでの範囲
    rectLocalX = centerOffsetX - vehicleLength / 2
    rectLocalY = vehicleWidth / 2 + startOffset
    rectWidth = vehicleLength
    rectHeight = width
  } else { // right
    // 右SCB: startOffsetからendOffsetまでの範囲（右方向は負）
    rectLocalX = centerOffsetX - vehicleLength / 2
    rectLocalY = -vehicleWidth / 2 - endOffset
    rectWidth = vehicleLength
    rectHeight = width
  }

  // 矩形の4隅（ローカル座標）
  const corners = [
    { x: rectLocalX, y: rectLocalY },
    { x: rectLocalX + rectWidth, y: rectLocalY },
    { x: rectLocalX + rectWidth, y: rectLocalY + rectHeight },
    { x: rectLocalX, y: rectLocalY + rectHeight }
  ]

  // ワールド座標に変換
  const worldCorners = corners.map(corner => {
    const rotatedX = corner.x * cos - corner.y * sin
    const rotatedY = corner.x * sin + corner.y * cos
    return new SAT.Vector(vehicleX + rotatedX, vehicleY + rotatedY)
  })

  return new SAT.Polygon(new SAT.Vector(0, 0), worldCorners)
}

/**
 * 4点から作成したポリゴン同士で衝突判定を実行
 * 車両本体とSCBの衝突判定も含む
 */
export function checkSCBCollisionsWithPolygons(
  egoPolygons: { body: SAT.Polygon | null, scb0: SAT.Polygon | null, scb1: SAT.Polygon | null, scb2: SAT.Polygon | null, scb3: SAT.Polygon | null },
  targetPolygons: { body: SAT.Polygon | null, scb0: SAT.Polygon | null, scb1: SAT.Polygon | null, scb2: SAT.Polygon | null, scb3: SAT.Polygon | null }
): SCBOverlapResult {
  const result: SCBOverlapResult = {
    level: 4,
    message: '安全',
    hasBigOBBOverlap: false,
    overlappedSCB: null,
    egoSCB1_vs_targetSCB: { scb1: false, scb2: false, scb3: false },
    egoSCB2_vs_targetSCB: { scb1: false, scb2: false, scb3: false },
    egoSCB3_vs_targetSCB: { scb1: false, scb2: false, scb3: false },
    targetSCB1_vs_egoSCB: { scb1: false, scb2: false, scb3: false },
    targetSCB2_vs_egoSCB: { scb1: false, scb2: false, scb3: false },
    targetSCB3_vs_egoSCB: { scb1: false, scb2: false, scb3: false }
  }

  let minCollisionLevel = 4

  // 車両本体同士の衝突判定（level -1：衝突）
  if (egoPolygons.body && targetPolygons.body) {
    const response = new SAT.Response()
    if (SAT.testPolygonPolygon(egoPolygons.body, targetPolygons.body, response)) {
      minCollisionLevel = -1
    }
  }

  // 自車両本体 vs 対象車両のSCB0（SD）
  if (egoPolygons.body && targetPolygons.scb0) {
    const response = new SAT.Response()
    if (SAT.testPolygonPolygon(egoPolygons.body, targetPolygons.scb0, response)) {
      minCollisionLevel = Math.min(minCollisionLevel, 0)
    }
  }

  // 自車両本体 vs 対象車両のSCB
  if (egoPolygons.body) {
    if (targetPolygons.scb1) {
      const response = new SAT.Response()
      if (SAT.testPolygonPolygon(egoPolygons.body, targetPolygons.scb1, response)) {
        result.targetSCB1_vs_egoSCB.scb1 = true
        minCollisionLevel = Math.min(minCollisionLevel, 1)
      }
    }
    if (targetPolygons.scb2) {
      const response = new SAT.Response()
      if (SAT.testPolygonPolygon(egoPolygons.body, targetPolygons.scb2, response)) {
        result.targetSCB2_vs_egoSCB.scb2 = true
        minCollisionLevel = Math.min(minCollisionLevel, 2)
      }
    }
    if (targetPolygons.scb3) {
      const response = new SAT.Response()
      if (SAT.testPolygonPolygon(egoPolygons.body, targetPolygons.scb3, response)) {
        result.targetSCB3_vs_egoSCB.scb3 = true
        minCollisionLevel = Math.min(minCollisionLevel, 3)
      }
    }
  }

  // 対象車両本体 vs 自車両のSCB0（SD）
  if (targetPolygons.body && egoPolygons.scb0) {
    const response = new SAT.Response()
    if (SAT.testPolygonPolygon(targetPolygons.body, egoPolygons.scb0, response)) {
      minCollisionLevel = Math.min(minCollisionLevel, 0)
    }
  }

  // 対象車両本体 vs 自車両のSCB
  if (targetPolygons.body) {
    if (egoPolygons.scb1) {
      const response = new SAT.Response()
      if (SAT.testPolygonPolygon(targetPolygons.body, egoPolygons.scb1, response)) {
        result.egoSCB1_vs_targetSCB.scb1 = true
        minCollisionLevel = Math.min(minCollisionLevel, 1)
      }
    }
    if (egoPolygons.scb2) {
      const response = new SAT.Response()
      if (SAT.testPolygonPolygon(targetPolygons.body, egoPolygons.scb2, response)) {
        result.egoSCB2_vs_targetSCB.scb2 = true
        minCollisionLevel = Math.min(minCollisionLevel, 2)
      }
    }
    if (egoPolygons.scb3) {
      const response = new SAT.Response()
      if (SAT.testPolygonPolygon(targetPolygons.body, egoPolygons.scb3, response)) {
        result.egoSCB3_vs_targetSCB.scb3 = true
        minCollisionLevel = Math.min(minCollisionLevel, 3)
      }
    }
  }

  // SCB0（SD）同士の衝突判定
  if (egoPolygons.scb0 && targetPolygons.scb0) {
    const response = new SAT.Response()
    if (SAT.testPolygonPolygon(egoPolygons.scb0, targetPolygons.scb0, response)) {
      minCollisionLevel = Math.min(minCollisionLevel, 0)
    }
  }

  // SCB1同士の衝突判定
  if (egoPolygons.scb1 && targetPolygons.scb1) {
    const response = new SAT.Response()
    if (SAT.testPolygonPolygon(egoPolygons.scb1, targetPolygons.scb1, response)) {
      result.egoSCB1_vs_targetSCB.scb1 = true
      result.targetSCB1_vs_egoSCB.scb1 = true
      minCollisionLevel = Math.min(minCollisionLevel, 1)
    }
  }

  // SCB2同士の衝突判定
  if (egoPolygons.scb2 && targetPolygons.scb2) {
    const response = new SAT.Response()
    if (SAT.testPolygonPolygon(egoPolygons.scb2, targetPolygons.scb2, response)) {
      result.egoSCB2_vs_targetSCB.scb2 = true
      result.targetSCB2_vs_egoSCB.scb2 = true
      minCollisionLevel = Math.min(minCollisionLevel, 2)
    }
  }

  // SCB3同士の衝突判定
  if (egoPolygons.scb3 && targetPolygons.scb3) {
    const response = new SAT.Response()
    if (SAT.testPolygonPolygon(egoPolygons.scb3, targetPolygons.scb3, response)) {
      result.egoSCB3_vs_targetSCB.scb3 = true
      result.targetSCB3_vs_egoSCB.scb3 = true
      minCollisionLevel = Math.min(minCollisionLevel, 3)
    }
  }

  // 衝突レベルに応じてメッセージを設定
  result.level = minCollisionLevel
  if (minCollisionLevel === -1) {
    result.message = '🚨 衝突（車両本体重複）'
    result.overlappedSCB = null
  } else if (minCollisionLevel === 0) {
    result.message = '⚠️ 極めて危険（SD重複）'
    result.overlappedSCB = null
  } else if (minCollisionLevel === 1) {
    result.message = '⚠️ 極めて危険（SCB1重複）'
    result.overlappedSCB = 'scb1'
  } else if (minCollisionLevel === 2) {
    result.message = '⚠️ 非常に危険（SCB2重複）'
    result.overlappedSCB = 'scb2'
  } else if (minCollisionLevel === 3) {
    result.message = '⚠️ 危険（SCB3重複）'
    result.overlappedSCB = 'scb3'
  } else {
    result.message = '安全'
    result.overlappedSCB = null
  }

  return result
}

/**
 * 自車SCBの詳細衝突情報から輪郭線スタイルを計算
 */
export function calculateEgoStrokeStyles(
  overlapLevel: number | undefined,
  overlapResult: SCBOverlapResult | undefined
): {
  strokeWidth0: number
  strokeWidth1: number
  strokeWidth2: number
  strokeWidth3: number
  strokeColor0: string | null
  strokeColor1: string | null
  strokeColor2: string | null
  strokeColor3: string | null
} {
  // デフォルト：枠線なし
  let strokeWidth0 = 0, strokeWidth1 = 0, strokeWidth2 = 0, strokeWidth3 = 0
  let strokeColor0 = null, strokeColor1 = null, strokeColor2 = null, strokeColor3 = null

  if (overlapLevel == null || overlapLevel === 4 || !overlapResult) {
    return { strokeWidth0, strokeWidth1, strokeWidth2, strokeWidth3, strokeColor0, strokeColor1, strokeColor2, strokeColor3 }
  }

  // SCB色の定義（濃い色：枠線用）
  const sdStrokeColor = 'rgb(255, 0, 0)'       // SD: 赤
  const scb1StrokeColor = 'rgb(204, 102, 0)'   // SCB1: 濃いオレンジ
  const scb2StrokeColor = 'rgb(204, 204, 0)'   // SCB2: 濃い黄色
  const scb3StrokeColor = 'rgb(0, 102, 204)'   // SCB3: 濃い水色

  const strokeWidth = 3

  // SD（SCB0）または車両本体の衝突時、すべてのSCB領域を不透明化
  if (overlapLevel <= 0) {
    strokeWidth0 = strokeWidth
    strokeColor0 = sdStrokeColor
    strokeWidth1 = strokeWidth
    strokeColor1 = scb1StrokeColor
    strokeWidth2 = strokeWidth
    strokeColor2 = scb2StrokeColor
    strokeWidth3 = strokeWidth
    strokeColor3 = scb3StrokeColor
    return { strokeWidth0, strokeWidth1, strokeWidth2, strokeWidth3, strokeColor0, strokeColor1, strokeColor2, strokeColor3 }
  }

  // 自車SCBが衝突しているかをチェック
  // 自車SCB vs 対象車SCB（同レベル）または対象車本体との衝突
  const egoSCB1Collides = overlapResult.egoSCB1_vs_targetSCB.scb1
  const egoSCB2Collides = overlapResult.egoSCB2_vs_targetSCB.scb2
  const egoSCB3Collides = overlapResult.egoSCB3_vs_targetSCB.scb3

  if (egoSCB1Collides) {
    strokeWidth1 = strokeWidth
    strokeColor1 = scb1StrokeColor
  }
  if (egoSCB2Collides) {
    strokeWidth2 = strokeWidth
    strokeColor2 = scb2StrokeColor
  }
  if (egoSCB3Collides) {
    strokeWidth3 = strokeWidth
    strokeColor3 = scb3StrokeColor
  }

  return { strokeWidth0, strokeWidth1, strokeWidth2, strokeWidth3, strokeColor0, strokeColor1, strokeColor2, strokeColor3 }
}

/**
 * 対象車SCBの詳細衝突情報から輪郭線スタイルを計算
 */
export function calculateTargetStrokeStyles(
  overlapLevel: number | undefined,
  overlapResult: SCBOverlapResult | undefined
): {
  strokeWidth0: number
  strokeWidth1: number
  strokeWidth2: number
  strokeWidth3: number
  strokeColor0: string | null
  strokeColor1: string | null
  strokeColor2: string | null
  strokeColor3: string | null
} {
  // デフォルト：枠線なし
  let strokeWidth0 = 0, strokeWidth1 = 0, strokeWidth2 = 0, strokeWidth3 = 0
  let strokeColor0 = null, strokeColor1 = null, strokeColor2 = null, strokeColor3 = null

  if (overlapLevel == null || overlapLevel === 4 || !overlapResult) {
    return { strokeWidth0, strokeWidth1, strokeWidth2, strokeWidth3, strokeColor0, strokeColor1, strokeColor2, strokeColor3 }
  }

  // SCB色の定義（濃い色：枠線用）
  const sdStrokeColor = 'rgb(255, 0, 0)'       // SD: 赤
  const scb1StrokeColor = 'rgb(204, 102, 0)'
  const scb2StrokeColor = 'rgb(204, 204, 0)'
  const scb3StrokeColor = 'rgb(0, 102, 204)'

  const strokeWidth = 3

  // SD（SCB0）または車両本体の衝突時、すべてのSCB領域を不透明化
  if (overlapLevel <= 0) {
    strokeWidth0 = strokeWidth
    strokeColor0 = sdStrokeColor
    strokeWidth1 = strokeWidth
    strokeColor1 = scb1StrokeColor
    strokeWidth2 = strokeWidth
    strokeColor2 = scb2StrokeColor
    strokeWidth3 = strokeWidth
    strokeColor3 = scb3StrokeColor
    return { strokeWidth0, strokeWidth1, strokeWidth2, strokeWidth3, strokeColor0, strokeColor1, strokeColor2, strokeColor3 }
  }

  // 対象車SCBが衝突しているかをチェック
  // 対象車SCB vs 自車SCB（同レベル）または自車本体との衝突
  const targetSCB1Collides = overlapResult.targetSCB1_vs_egoSCB.scb1
  const targetSCB2Collides = overlapResult.targetSCB2_vs_egoSCB.scb2
  const targetSCB3Collides = overlapResult.targetSCB3_vs_egoSCB.scb3

  if (targetSCB1Collides) {
    strokeWidth1 = strokeWidth
    strokeColor1 = scb1StrokeColor
  }
  if (targetSCB2Collides) {
    strokeWidth2 = strokeWidth
    strokeColor2 = scb2StrokeColor
  }
  if (targetSCB3Collides) {
    strokeWidth3 = strokeWidth
    strokeColor3 = scb3StrokeColor
  }

  return { strokeWidth0, strokeWidth1, strokeWidth2, strokeWidth3, strokeColor0, strokeColor1, strokeColor2, strokeColor3 }
}
