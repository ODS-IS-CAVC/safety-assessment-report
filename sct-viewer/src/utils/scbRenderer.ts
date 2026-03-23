import SAT from 'sat'
import {
  calculateEgoStrokeStyles,
  calculateTargetStrokeStyles,
  createIncrementalSCBPolygon,
  type SCBOverlapResult
} from './scbUtils'
import {
  SHOW_SCB_DEBUG_BOUNDS,
  SHOW_COLLISION_POLYGONS,
  SD_COLOR,
  SCB1_COLOR,
  SCB2_COLOR,
  SCB3_COLOR,
} from './renderConstants'
import { VehiclePosition } from '../types'

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

/** SCBポリゴンセット（4段階） */
export interface SCBPolygonSet {
  scb0: SAT.Polygon | null
  scb1: SAT.Polygon | null
  scb2: SAT.Polygon | null
  scb3: SAT.Polygon | null
}

/** 車両＋SCBポリゴンセット */
export interface VehicleSCBPolygons {
  body: SAT.Polygon | null
  scb0: SAT.Polygon | null
  scb1: SAT.Polygon | null
  scb2: SAT.Polygon | null
  scb3: SAT.Polygon | null
}

/** SCB描画に必要なコンテキスト */
export interface SCBDrawContext {
  ctx: CanvasRenderingContext2D
  zoom: number
  rotationRad: number
  boundingBox: { minX: number; minY: number; baseScale: number; margin: number } | null
  rotateAndTransform: (x: number, y: number) => [number, number]
  getVehicleBBox: (vehicleId: string) => { Dimensions: { length: number; width: number }; Center: { x: number } } | null
}

/** SCB値セット（4段階） */
interface SCBValues {
  sd: number
  scb1: number
  scb2: number
  scb3: number
}

// ---------------------------------------------------------------------------
// SCB描画の内部共通ロジック
// ---------------------------------------------------------------------------

/** strokeStylesの型 */
interface StrokeStyles {
  strokeWidth0: number; strokeWidth1: number; strokeWidth2: number; strokeWidth3: number
  strokeColor0: string | null; strokeColor1: string | null; strokeColor2: string | null; strokeColor3: string | null
}

/** onlyColliding分岐に応じてSCBを描画する共通関数 */
function renderSCBByCollisionState(
  drawSCBBox: (value: number, scbType: 'scb0' | 'scb1' | 'scb2' | 'scb3', color: string, strokeWidth?: number, strokeColor?: string) => void,
  scbValues: SCBValues,
  strokeStyles: StrokeStyles,
  onlyColliding?: boolean
) {
  const { sd, scb1, scb2, scb3 } = scbValues
  const { strokeWidth0, strokeWidth1, strokeWidth2, strokeWidth3, strokeColor0, strokeColor1, strokeColor2, strokeColor3 } = strokeStyles

  // 衝突していないSCBを描画（奥から: SD → SCB3 → SCB2 → SCB1）
  const drawNonColliding = () => {
    if (strokeWidth0 === 0) drawSCBBox(sd, 'scb0', SD_COLOR)
    if (strokeWidth3 === 0) drawSCBBox(scb3, 'scb3', SCB3_COLOR)
    if (strokeWidth2 === 0) drawSCBBox(scb2, 'scb2', SCB2_COLOR)
    if (strokeWidth1 === 0) drawSCBBox(scb1, 'scb1', SCB1_COLOR)
  }

  // 衝突しているSCBを描画
  const drawColliding = () => {
    if (strokeWidth0 > 0 && strokeColor0) drawSCBBox(sd, 'scb0', SD_COLOR, strokeWidth0, strokeColor0)
    if (strokeWidth3 > 0 && strokeColor3) drawSCBBox(scb3, 'scb3', SCB3_COLOR, strokeWidth3, strokeColor3)
    if (strokeWidth2 > 0 && strokeColor2) drawSCBBox(scb2, 'scb2', SCB2_COLOR, strokeWidth2, strokeColor2)
    if (strokeWidth1 > 0 && strokeColor1) drawSCBBox(scb1, 'scb1', SCB1_COLOR, strokeWidth1, strokeColor1)
  }

  if (onlyColliding === false) {
    drawNonColliding()
  } else if (onlyColliding === true) {
    drawColliding()
  } else {
    drawNonColliding()
    drawColliding()
  }
}

/** SCB増分オフセットを計算する */
function getSCBIncrementalOffsets(
  scbType: 'scb0' | 'scb1' | 'scb2' | 'scb3',
  scbValues: SCBValues
): { startOffset: number; endOffset: number } {
  if (scbType === 'scb0') return { startOffset: 0, endOffset: scbValues.sd }
  if (scbType === 'scb1') return { startOffset: scbValues.sd, endOffset: scbValues.scb1 }
  if (scbType === 'scb2') return { startOffset: scbValues.scb1, endOffset: scbValues.scb2 }
  return { startOffset: scbValues.scb2, endOffset: scbValues.scb3 }
}

/** SCB矩形を描画する共通関数（塗りつぶし＋枠線） */
function fillAndStrokeSCBRect(
  ctx: CanvasRenderingContext2D,
  rectX: number, rectY: number,
  rectWidth: number, rectHeight: number,
  color: string,
  strokeWidth?: number,
  strokeColor?: string
) {
  // 塗りつぶし（衝突時は完全不透明、通常時は半透明）
  ctx.fillStyle = color
  ctx.globalAlpha = (strokeWidth && strokeColor) ? 1.0 : 0.3
  ctx.fillRect(rectX, rectY, rectWidth, rectHeight)
  ctx.globalAlpha = 1.0

  // 枠線描画
  ctx.strokeStyle = (strokeWidth && strokeColor) ? strokeColor : color
  ctx.lineWidth = (strokeWidth && strokeColor) ? strokeWidth : 1
  ctx.strokeRect(rectX, rectY, rectWidth, rectHeight)
}

// ---------------------------------------------------------------------------
// 公開API: 縦方向SCB描画
// ---------------------------------------------------------------------------

/** 縦方向（前後方向）SCB領域を描画 */
export function drawLongitudinalSCBRegions(
  drawCtx: SCBDrawContext,
  vehiclePos: VehiclePosition,
  sdx: number | null | undefined,
  scb1x: number | null | undefined,
  scb2x: number | null | undefined,
  scb3x: number | null | undefined,
  direction: 'forward' | 'backward',
  overlapLevel?: number,
  overlapResult?: SCBOverlapResult,
  onlyColliding?: boolean,
  useTargetStyles?: boolean
): SCBPolygonSet {
  const nullResult: SCBPolygonSet = { scb0: null, scb1: null, scb2: null, scb3: null }

  // SCB値が無効な場合はスキップ
  if (sdx == null || scb1x == null || scb2x == null || scb3x == null) return nullResult
  if (isNaN(sdx) || isNaN(scb1x) || isNaN(scb2x) || isNaN(scb3x)) return nullResult

  const bbox = drawCtx.getVehicleBBox(vehiclePos.vehicleId)
  if (!bbox) return nullResult

  const { ctx, zoom, rotationRad, boundingBox } = drawCtx
  const vehicleLength = bbox.Dimensions.length
  const vehicleWidth = bbox.Dimensions.width
  const centerOffsetX = bbox.Center.x
  const scale = zoom * (boundingBox?.baseScale || 1)

  const [vehicleCanvasX, vehicleCanvasY] = drawCtx.rotateAndTransform(vehiclePos.x, vehiclePos.y)
  const scaledLength = vehicleLength * scale
  const scaledWidth = vehicleWidth * scale
  const scaledCenterOffset = centerOffsetX * scale

  const scbValues: SCBValues = { sd: sdx, scb1: scb1x, scb2: scb2x, scb3: scb3x }

  // ワールド座標のポリゴンを保存
  const worldPolygons: SCBPolygonSet = { scb0: null, scb1: null, scb2: null, scb3: null }

  // Canvas transformを1回だけ実行
  ctx.save()
  ctx.translate(vehicleCanvasX, vehicleCanvasY)
  ctx.rotate(-vehiclePos.heading - rotationRad)

  // 縦方向SCB矩形描画関数
  const drawSCBBoxX = (
    scbX: number,
    scbType: 'scb0' | 'scb1' | 'scb2' | 'scb3',
    color: string,
    strokeW?: number,
    strokeC?: string
  ) => {
    if (scbX <= 0) return

    const { startOffset, endOffset } = getSCBIncrementalOffsets(scbType, scbValues)

    // ローカル座標のポリゴンを作成（描画用）
    const localPolygon = createIncrementalSCBPolygon(
      0, 0, 0,
      vehicleLength, vehicleWidth, centerOffsetX,
      startOffset, endOffset, direction
    )
    if (!localPolygon) return

    const points = localPolygon.calcPoints
    if (points.length < 4) return

    // ワールド座標のポリゴンを作成（衝突判定用）
    const worldPolygon = createIncrementalSCBPolygon(
      vehiclePos.x, vehiclePos.y, vehiclePos.heading,
      vehicleLength, vehicleWidth, centerOffsetX,
      startOffset, endOffset, direction, true
    )
    if (scbType === 'scb0') worldPolygons.scb0 = worldPolygon
    else if (scbType === 'scb1') worldPolygons.scb1 = worldPolygon
    else if (scbType === 'scb2') worldPolygons.scb2 = worldPolygon
    else worldPolygons.scb3 = worldPolygon

    // 矩形の位置とサイズを計算
    const x0 = points[0].x, y0 = points[0].y
    const x2 = points[2].x, y2 = points[2].y
    const rectX = Math.min(x0, x2) * scale
    const rectY = Math.min(y0, y2) * scale
    const rectWidth = Math.abs(x2 - x0) * scale
    const rectHeight = Math.abs(y2 - y0) * scale

    fillAndStrokeSCBRect(ctx, rectX, rectY, rectWidth, rectHeight, color, strokeW, strokeC)
  }

  // 詳細衝突情報に応じて輪郭線スタイルを計算
  const strokeStyles = useTargetStyles
    ? calculateTargetStrokeStyles(overlapLevel, overlapResult)
    : calculateEgoStrokeStyles(overlapLevel, overlapResult)

  // デバッグ用：大きなOBBを緑点線で描画
  if (SHOW_SCB_DEBUG_BOUNDS) {
    const maxScbX = Math.max(sdx, scb1x, scb2x, scb3x)
    const scaledMaxScbX = maxScbX * scale
    const bigX = direction === 'forward'
      ? scaledCenterOffset - scaledLength / 2
      : scaledCenterOffset + scaledLength / 2 - scaledLength - scaledMaxScbX
    const bigWidth = scaledLength + scaledMaxScbX

    ctx.strokeStyle = 'rgb(0, 255, 0)'
    ctx.lineWidth = 2
    ctx.setLineDash([5, 5])
    ctx.strokeRect(bigX, -scaledWidth / 2, bigWidth, scaledWidth)
    ctx.setLineDash([])
  }

  // onlyCollidingパラメータに応じて描画を制御
  renderSCBByCollisionState(drawSCBBoxX, scbValues, strokeStyles, onlyColliding)

  ctx.restore()
  return worldPolygons
}

// ---------------------------------------------------------------------------
// 公開API: 横方向SCB描画
// ---------------------------------------------------------------------------

/** 横方向SCB領域を描画 */
export function drawLateralSCBRegions(
  drawCtx: SCBDrawContext,
  vehiclePos: VehiclePosition,
  egoPos: VehiclePosition,
  t2_x: number | null | undefined,
  t2_y: number | null | undefined,
  sdy: number | null | undefined,
  scb1y: number | null | undefined,
  scb2y: number | null | undefined,
  scb3y: number | null | undefined,
  overlapLevel?: number,
  overlapResult?: SCBOverlapResult,
  onlyColliding?: boolean,
  useEgoStyles?: boolean
): SCBPolygonSet {
  const nullResult: SCBPolygonSet = { scb0: null, scb1: null, scb2: null, scb3: null }

  if (sdy == null || scb1y == null || scb2y == null || scb3y == null) return nullResult
  if (isNaN(sdy) || isNaN(scb1y) || isNaN(scb2y) || isNaN(scb3y)) return nullResult

  const bbox = drawCtx.getVehicleBBox(vehiclePos.vehicleId)
  if (!bbox) return nullResult

  const { ctx, zoom, rotationRad, boundingBox } = drawCtx
  const vehicleLength = bbox.Dimensions.length
  const vehicleWidth = bbox.Dimensions.width
  const centerOffsetX = bbox.Center.x
  const scale = zoom * (boundingBox?.baseScale || 1)

  const [vehicleCanvasX, vehicleCanvasY] = drawCtx.rotateAndTransform(vehiclePos.x, vehiclePos.y)
  const scaledLength = vehicleLength * scale
  const scaledCenterOffset = centerOffsetX * scale

  // T2点からSCBの方向を判定
  let t2OffsetY = 0
  if (t2_x != null && t2_y != null && !isNaN(t2_x) && !isNaN(t2_y)) {
    const dx_t2 = t2_x - vehiclePos.x
    const dy_t2 = t2_y - vehiclePos.y
    const cos_ego = Math.cos(egoPos.heading)
    const sin_ego = Math.sin(egoPos.heading)
    t2OffsetY = dx_t2 * sin_ego - dy_t2 * cos_ego
  }
  const isT2OnLeft = t2OffsetY > 0

  const scbValues: SCBValues = { sd: sdy, scb1: scb1y, scb2: scb2y, scb3: scb3y }
  const worldPolygons: SCBPolygonSet = { scb0: null, scb1: null, scb2: null, scb3: null }

  // 横方向SCB矩形描画関数
  const drawSCBBoxY = (
    scbY: number,
    scbType: 'scb0' | 'scb1' | 'scb2' | 'scb3',
    color: string,
    strokeW?: number,
    strokeC?: string
  ) => {
    if (scbY <= 0) return

    ctx.save()
    ctx.translate(vehicleCanvasX, vehicleCanvasY)
    ctx.rotate(-egoPos.heading - rotationRad)

    const { startOffset, endOffset } = getSCBIncrementalOffsets(scbType, scbValues)
    const scbDirection: 'left' | 'right' = isT2OnLeft ? 'left' : 'right'

    // ローカル座標のポリゴン
    const localPolygon = createIncrementalSCBPolygon(
      0, 0, 0,
      vehicleLength, vehicleWidth, centerOffsetX,
      startOffset, endOffset, scbDirection
    )
    if (!localPolygon) { ctx.restore(); return }

    const points = localPolygon.calcPoints
    if (points.length < 4) { ctx.restore(); return }

    // ワールド座標のポリゴン（衝突判定用、方向反転）
    const invertedDirection: 'left' | 'right' = scbDirection === 'left' ? 'right' : 'left'
    const worldPolygon = createIncrementalSCBPolygon(
      vehiclePos.x, vehiclePos.y, egoPos.heading,
      vehicleLength, vehicleWidth, centerOffsetX,
      startOffset, endOffset, invertedDirection, false
    )
    if (scbType === 'scb0') worldPolygons.scb0 = worldPolygon
    else if (scbType === 'scb1') worldPolygons.scb1 = worldPolygon
    else if (scbType === 'scb2') worldPolygons.scb2 = worldPolygon
    else worldPolygons.scb3 = worldPolygon

    // 矩形描画
    const x0 = points[0].x, y0 = points[0].y
    const x2 = points[2].x, y2 = points[2].y
    const rectX = Math.min(x0, x2) * scale
    const rectY = Math.min(y0, y2) * scale
    const rectWidth = Math.abs(x2 - x0) * scale
    const rectHeight = Math.abs(y2 - y0) * scale

    fillAndStrokeSCBRect(ctx, rectX, rectY, rectWidth, rectHeight, color, strokeW, strokeC)
    ctx.restore()
  }

  // 詳細衝突情報に応じて輪郭線スタイルを計算
  const strokeStyles = useEgoStyles
    ? calculateEgoStrokeStyles(overlapLevel, overlapResult)
    : calculateTargetStrokeStyles(overlapLevel, overlapResult)

  // デバッグ用：大きなOBBを緑点線で描画
  if (SHOW_SCB_DEBUG_BOUNDS) {
    const maxScbY = Math.max(sdy, scb1y, scb2y, scb3y)
    ctx.save()
    ctx.translate(vehicleCanvasX, vehicleCanvasY)
    ctx.rotate(-egoPos.heading - rotationRad)

    const scaledMaxScbY = maxScbY * scale
    const scaledT2OffsetY = t2OffsetY * scale
    const bigX = -scaledLength / 2 + scaledCenterOffset
    const bigY = isT2OnLeft ? scaledT2OffsetY : scaledT2OffsetY - scaledMaxScbY

    ctx.strokeStyle = 'rgb(0, 255, 0)'
    ctx.lineWidth = 2
    ctx.setLineDash([5, 5])
    ctx.strokeRect(bigX, bigY, scaledLength, scaledMaxScbY)
    ctx.setLineDash([])
    ctx.restore()
  }

  renderSCBByCollisionState(drawSCBBoxY, scbValues, strokeStyles, onlyColliding)
  return worldPolygons
}

// ---------------------------------------------------------------------------
// 公開API: デバッグ描画
// ---------------------------------------------------------------------------

/** デバッグ用：衝突判定用ポリゴンを描画 */
export function drawDebugCollisionPolygons(
  ctx: CanvasRenderingContext2D,
  egoPolygons: VehicleSCBPolygons,
  targetPolygons: VehicleSCBPolygons,
  rotateAndTransform: (x: number, y: number) => [number, number]
) {
  if (!SHOW_COLLISION_POLYGONS) return

  const drawPolygon = (polygon: SAT.Polygon | null, color: string, label: string) => {
    if (!polygon) return

    ctx.save()
    const worldPoints = polygon.calcPoints
    if (worldPoints.length < 3) { ctx.restore(); return }

    ctx.beginPath()
    const [x0, y0] = rotateAndTransform(worldPoints[0].x, worldPoints[0].y)
    ctx.moveTo(x0, y0)
    for (let i = 1; i < worldPoints.length; i++) {
      const [x, y] = rotateAndTransform(worldPoints[i].x, worldPoints[i].y)
      ctx.lineTo(x, y)
    }
    ctx.closePath()

    ctx.fillStyle = color.replace('rgb', 'rgba').replace(')', ', 0.3)')
    ctx.fill()

    ctx.strokeStyle = color
    ctx.lineWidth = 3
    ctx.setLineDash([])
    ctx.stroke()

    ctx.font = 'bold 14px monospace'
    const textMetrics = ctx.measureText(label)
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
    ctx.fillRect(x0 + 5, y0 - 20, textMetrics.width + 6, 18)
    ctx.fillStyle = 'white'
    ctx.fillText(label, x0 + 8, y0 - 5)
    ctx.restore()
  }

  // 自車ポリゴン（赤系）
  drawPolygon(egoPolygons.body, 'rgb(128, 0, 0)', 'Ego Body')
  drawPolygon(egoPolygons.scb1, 'rgb(255, 0, 0)', 'Ego SCB1')
  drawPolygon(egoPolygons.scb2, 'rgb(255, 100, 100)', 'Ego SCB2')
  drawPolygon(egoPolygons.scb3, 'rgb(255, 150, 150)', 'Ego SCB3')

  // 対象車ポリゴン（青系）
  drawPolygon(targetPolygons.body, 'rgb(0, 0, 128)', 'Target Body')
  drawPolygon(targetPolygons.scb1, 'rgb(0, 0, 255)', 'Target SCB1')
  drawPolygon(targetPolygons.scb2, 'rgb(100, 100, 255)', 'Target SCB2')
  drawPolygon(targetPolygons.scb3, 'rgb(150, 150, 255)', 'Target SCB3')
}

/** 衝突判定用ポリゴンを点線で描画 */
export function drawCollisionPolygon(
  ctx: CanvasRenderingContext2D,
  polygon: SAT.Polygon,
  color: string,
  rotateAndTransform: (x: number, y: number) => [number, number]
) {
  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = 3
  ctx.setLineDash([5, 5])
  ctx.globalAlpha = 0.7

  ctx.beginPath()
  const points = polygon.calcPoints
  if (points.length > 0) {
    const [firstX, firstY] = rotateAndTransform(points[0].x, points[0].y)
    ctx.moveTo(firstX, firstY)
    for (let i = 1; i < points.length; i++) {
      const [x, y] = rotateAndTransform(points[i].x, points[i].y)
      ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.stroke()
  }

  ctx.globalAlpha = 1.0
  ctx.setLineDash([])
  ctx.restore()
}

// 衝突判定と描画のためにre-export
export { checkSCBCollisionsWithPolygons, createVehicleOBBPolygon, createSCBPolygon } from './scbUtils'
export type { SCBOverlapResult } from './scbUtils'
