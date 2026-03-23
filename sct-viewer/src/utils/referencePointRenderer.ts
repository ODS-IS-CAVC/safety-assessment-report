import { VehiclePosition, SCTDataset, SCTRow } from '../types'
import { SCBDisplayMode } from '../components/RenderingControls'
import {
  SHOW_REFERENCE_POINT_LABELS,
  MARKER_S1_COLOR,
  MARKER_T1_COLOR,
  MARKER_P1_COLOR,
  MARKER_T2_COLOR,
  MARKER_P2_COLOR,
} from './renderConstants'
import { findPositionAtTime, findFrameIndexAtTime } from './trajectoryRenderer'

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

/** 参照点描画に必要なコンテキスト */
interface ReferencePointDrawContext {
  ctx: CanvasRenderingContext2D
  rotateAndTransform: (x: number, y: number) => [number, number]
  getVehicleBBox: (vehicleId: string) => { Dimensions: { length: number; width: number }; Center: { x: number } } | null
}

// ---------------------------------------------------------------------------
// 内部ヘルパー
// ---------------------------------------------------------------------------

/** 丸マーカーを描画 */
function drawCircleMarker(
  ctx: CanvasRenderingContext2D,
  canvasX: number, canvasY: number,
  radius: number, fillColor: string,
  label?: string
) {
  ctx.save()
  ctx.fillStyle = fillColor
  ctx.beginPath()
  ctx.arc(canvasX, canvasY, radius, 0, 2 * Math.PI)
  ctx.fill()
  if (label && SHOW_REFERENCE_POINT_LABELS) {
    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 14px "Courier New", monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, canvasX, canvasY)
  }
  ctx.restore()
}

/** ローカル座標をグローバル座標に変換してCanvas座標に変換 */
function transformVertex(
  localX: number, localY: number,
  baseX: number, baseY: number,
  heading: number,
  rotateAndTransform: (x: number, y: number) => [number, number]
): [number, number] {
  const globalX = baseX + localX * Math.cos(heading) - localY * Math.sin(heading)
  const globalY = baseY + localX * Math.sin(heading) + localY * Math.cos(heading)
  return rotateAndTransform(globalX, globalY)
}

// ---------------------------------------------------------------------------
// 車両後軸中央マーカー
// ---------------------------------------------------------------------------

/** 全車両の後軸中央を可視化 */
export function drawVehicleCenterMarkers(
  ctx: CanvasRenderingContext2D,
  egoTrajectory: VehiclePosition[] | null,
  targetTrajectories: VehiclePosition[][],
  currentTime: number,
  rotateAndTransform: (x: number, y: number) => [number, number]
) {
  // 自車両
  if (egoTrajectory) {
    const egoPos = findPositionAtTime(egoTrajectory, currentTime)
    if (egoPos) {
      const [canvasX, canvasY] = rotateAndTransform(egoPos.x, egoPos.y)
      ctx.save()
      ctx.strokeStyle = '#FFFF00'
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.arc(canvasX, canvasY, 8, 0, 2 * Math.PI)
      ctx.stroke()
      ctx.fillStyle = '#FF0000'
      ctx.beginPath()
      ctx.arc(canvasX, canvasY, 6, 0, 2 * Math.PI)
      ctx.fill()
      ctx.restore()
    }
  }

  // 対象車両（全て）
  targetTrajectories.forEach((trajectory) => {
    const targetPos = findPositionAtTime(trajectory, currentTime)
    if (targetPos) {
      const [canvasX, canvasY] = rotateAndTransform(targetPos.x, targetPos.y)
      ctx.save()
      ctx.strokeStyle = '#FFFF00'
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.arc(canvasX, canvasY, 8, 0, 2 * Math.PI)
      ctx.stroke()
      ctx.fillStyle = '#0000FF'
      ctx.beginPath()
      ctx.arc(canvasX, canvasY, 6, 0, 2 * Math.PI)
      ctx.fill()
      ctx.restore()
    }
  })
}

// ---------------------------------------------------------------------------
// P6仕様の計算参照点マーカー
// ---------------------------------------------------------------------------

/** S1, P1, T2, P2マーカーを描画 */
function drawReferenceMarkers(
  drawCtx: ReferencePointDrawContext,
  sctRow: SCTRow,
  egoPos: VehiclePosition
) {
  const { ctx, rotateAndTransform } = drawCtx

  if (sctRow.s1_x === undefined || sctRow.s1_y === undefined ||
      sctRow.t1_x === undefined || sctRow.t1_y === undefined ||
      sctRow.p0_x === undefined || sctRow.p0_y === undefined ||
      sctRow.p1_x === undefined || sctRow.p1_y === undefined) return

  // S1: 自車OBB最近点
  const [s1CanvasX, s1CanvasY] = rotateAndTransform(sctRow.s1_x, sctRow.s1_y)
  drawCircleMarker(ctx, s1CanvasX, s1CanvasY, 6, MARKER_S1_COLOR, 'S1')

  // P1: 軌跡上T1最近点
  const [p1CanvasX, p1CanvasY] = rotateAndTransform(sctRow.p1_x, sctRow.p1_y)
  drawCircleMarker(ctx, p1CanvasX, p1CanvasY, 6, MARKER_P1_COLOR, 'P1')

  // T2とP2マーカー
  if (sctRow.t2_x === undefined || sctRow.t2_y === undefined ||
      sctRow.p2_x === undefined || sctRow.p2_y === undefined) return

  // T2表示判定: P2→T2距離がS1オフセットより大きい場合のみ表示
  const dx_to_t2 = sctRow.t2_x - sctRow.p2_x
  const dy_to_t2 = sctRow.t2_y - sctRow.p2_y
  const dist_p2_to_t2 = Math.sqrt(dx_to_t2 * dx_to_t2 + dy_to_t2 * dy_to_t2)

  const cos_h = Math.cos(egoPos.heading)
  const sin_h = Math.sin(egoPos.heading)
  const s1_rel_x = sctRow.s1_x - egoPos.x
  const s1_rel_y = sctRow.s1_y - egoPos.y
  const s1_dy_local = -s1_rel_x * sin_h + s1_rel_y * cos_h
  const s1_offset = Math.abs(s1_dy_local)

  const shouldShowT2 = dist_p2_to_t2 > s1_offset + 0.3

  if (shouldShowT2) {
    const [t2CanvasX, t2CanvasY] = rotateAndTransform(sctRow.t2_x, sctRow.t2_y)
    drawCircleMarker(ctx, t2CanvasX, t2CanvasY, 6, MARKER_T2_COLOR, 'T2')
  }

  // P2: 軌跡上T2最近点
  const [p2CanvasX, p2CanvasY] = rotateAndTransform(sctRow.p2_x, sctRow.p2_y)
  drawCircleMarker(ctx, p2CanvasX, p2CanvasY, 6, MARKER_P2_COLOR, 'P2')
}

/** T1マーカーとS1-T1間の線を描画（最前面） */
function drawT1Marker(
  drawCtx: ReferencePointDrawContext,
  sctRow: SCTRow
) {
  const { ctx, rotateAndTransform } = drawCtx

  if (sctRow.s1_x === undefined || sctRow.s1_y === undefined ||
      sctRow.t1_x === undefined || sctRow.t1_y === undefined ||
      isNaN(sctRow.t1_x) || isNaN(sctRow.t1_y)) return

  const [s1CanvasX, s1CanvasY] = rotateAndTransform(sctRow.s1_x, sctRow.s1_y)
  const [t1CanvasX, t1CanvasY] = rotateAndTransform(sctRow.t1_x, sctRow.t1_y)

  // S1-T1間の線
  ctx.save()
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)'
  ctx.lineWidth = 1
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  ctx.moveTo(s1CanvasX, s1CanvasY)
  ctx.lineTo(t1CanvasX, t1CanvasY)
  ctx.stroke()
  ctx.restore()

  // T1マーカー
  drawCircleMarker(ctx, t1CanvasX, t1CanvasY, 6, MARKER_T1_COLOR, 'T1')
}

// ---------------------------------------------------------------------------
// 車両頂点マーカー
// ---------------------------------------------------------------------------

/** 車両の4頂点にマーカーを描画 */
function drawVehicleVertexMarkers(
  drawCtx: ReferencePointDrawContext,
  vehiclePos: VehiclePosition,
  fillColor: string
) {
  const { ctx, rotateAndTransform, getVehicleBBox } = drawCtx
  const bbox = getVehicleBBox(vehiclePos.vehicleId)
  if (!bbox) return

  const len = bbox.Dimensions.length
  const wid = bbox.Dimensions.width
  const cx = bbox.Center.x
  const vertexRadius = 4

  const vertices = [
    { x: cx + len / 2, y: -wid / 2 },  // 前右
    { x: cx + len / 2, y: wid / 2 },   // 前左
    { x: cx - len / 2, y: -wid / 2 },  // 後右
    { x: cx - len / 2, y: wid / 2 },   // 後左
  ]

  ctx.save()
  ctx.fillStyle = fillColor
  vertices.forEach(v => {
    const [canvasX, canvasY] = transformVertex(v.x, v.y, vehiclePos.x, vehiclePos.y, vehiclePos.heading, rotateAndTransform)
    ctx.beginPath()
    ctx.arc(canvasX, canvasY, vertexRadius, 0, 2 * Math.PI)
    ctx.fill()
  })
  ctx.restore()
}

// ---------------------------------------------------------------------------
// DX/DY可視化線
// ---------------------------------------------------------------------------

/** DX可視化線を描画（自車前端/後端からP1まで） */
function drawDXVisualization(
  drawCtx: ReferencePointDrawContext,
  sctRow: SCTRow,
  egoPos: VehiclePosition,
  egoTrajectory: VehiclePosition[],
  currentTime: number
) {
  const { ctx, rotateAndTransform, getVehicleBBox } = drawCtx
  const dx = sctRow.dx
  if (dx === null || dx === undefined || isNaN(dx)) return
  if (sctRow.p1_x === undefined || sctRow.p1_y === undefined || isNaN(sctRow.p1_x) || isNaN(sctRow.p1_y)) return

  const egoBbox = getVehicleBBox(egoPos.vehicleId)
  const egoFrontOffsetX = (egoBbox?.Center.x || 0) + (egoBbox?.Dimensions.length || 0) / 2

  ctx.save()

  if (dx >= 0) {
    // 前方: 自車前端からP1まで軌跡に沿って描画
    const cos = Math.cos(egoPos.heading)
    const sin = Math.sin(egoPos.heading)
    const egoFrontX = egoPos.x + egoFrontOffsetX * cos
    const egoFrontY = egoPos.y + egoFrontOffsetX * sin

    ctx.strokeStyle = 'rgba(255, 69, 0, 0.9)'
    ctx.lineWidth = 3
    ctx.beginPath()

    const [frontCanvasX, frontCanvasY] = rotateAndTransform(egoFrontX, egoFrontY)
    ctx.moveTo(frontCanvasX, frontCanvasY)

    const frameIndex = findFrameIndexAtTime(egoTrajectory, currentTime)
    const p1WorldX = sctRow.p1_x
    const p1WorldY = sctRow.p1_y

    for (let i = frameIndex; i < egoTrajectory.length; i++) {
      const point = egoTrajectory[i]
      const pointCos = Math.cos(point.heading)
      const pointSin = Math.sin(point.heading)
      const currX = point.x + egoFrontOffsetX * pointCos
      const currY = point.y + egoFrontOffsetX * pointSin

      const [canvasX, canvasY] = rotateAndTransform(currX, currY)
      ctx.lineTo(canvasX, canvasY)

      const distToP1 = Math.sqrt((currX - p1WorldX) ** 2 + (currY - p1WorldY) ** 2)
      if (distToP1 < 1.0) break
    }

    const [p1CanvasX, p1CanvasY] = rotateAndTransform(p1WorldX, p1WorldY)
    ctx.lineTo(p1CanvasX, p1CanvasY)
    ctx.stroke()
    ctx.restore()

    // DXラベル
    const midCanvasX = (frontCanvasX + p1CanvasX) / 2
    const midCanvasY = (frontCanvasY + p1CanvasY) / 2
    ctx.save()
    ctx.fillStyle = 'rgba(255, 255, 255, 1.0)'
    ctx.font = 'bold 14px Arial'
    ctx.textAlign = 'center'
    ctx.fillText(`dx: ${Math.abs(dx).toFixed(1)}m`, midCanvasX, midCanvasY - 10)
    ctx.restore()
  } else {
    // 後方: 自車後端からP1まで直線で描画
    const egoBBox = getVehicleBBox(egoPos.vehicleId)
    if (!egoBBox || !egoBBox.Center || !egoBBox.Dimensions) {
      ctx.restore()
      return
    }

    ctx.strokeStyle = 'rgba(255, 69, 0, 0.9)'
    ctx.lineWidth = 3
    ctx.beginPath()

    const egoRearOffsetX = egoBBox.Center.x - egoBBox.Dimensions.length / 2
    const egoRearX = egoPos.x + egoRearOffsetX * Math.cos(egoPos.heading)
    const egoRearY = egoPos.y + egoRearOffsetX * Math.sin(egoPos.heading)

    const [rearCanvasX, rearCanvasY] = rotateAndTransform(egoRearX, egoRearY)
    ctx.moveTo(rearCanvasX, rearCanvasY)

    const [p1CanvasX, p1CanvasY] = rotateAndTransform(sctRow.p1_x, sctRow.p1_y)
    ctx.lineTo(p1CanvasX, p1CanvasY)
    ctx.stroke()
    ctx.restore()

    // DXラベル
    const midCanvasX = (rearCanvasX + p1CanvasX) / 2
    const midCanvasY = (rearCanvasY + p1CanvasY) / 2
    ctx.save()
    ctx.fillStyle = 'rgba(255, 255, 255, 1.0)'
    ctx.font = 'bold 14px Arial'
    ctx.textAlign = 'center'
    ctx.fillText(`dx: ${Math.abs(dx).toFixed(1)}m`, midCanvasX, midCanvasY - 10)
    ctx.restore()
  }
}

/** DY可視化線を描画（P2からT2への線） */
function drawDYVisualization(
  drawCtx: ReferencePointDrawContext,
  sctRow: SCTRow,
  egoPos: VehiclePosition,
  dy: number
) {
  const { ctx, rotateAndTransform } = drawCtx

  if (sctRow.t2_x === undefined || sctRow.t2_y === undefined ||
      sctRow.p2_x === undefined || sctRow.p2_y === undefined ||
      sctRow.s1_x === undefined || sctRow.s1_y === undefined ||
      isNaN(sctRow.t2_x) || isNaN(sctRow.p2_x)) return

  const dx_to_t2 = sctRow.t2_x - sctRow.p2_x
  const dy_to_t2 = sctRow.t2_y - sctRow.p2_y
  const dist_p2_to_t2 = Math.sqrt(dx_to_t2 * dx_to_t2 + dy_to_t2 * dy_to_t2)

  if (dist_p2_to_t2 <= 0.01) return

  const unit_x = dx_to_t2 / dist_p2_to_t2
  const unit_y = dy_to_t2 / dist_p2_to_t2

  // S1オフセット距離を計算
  const cos_h = Math.cos(egoPos.heading)
  const sin_h = Math.sin(egoPos.heading)
  const s1_rel_x = sctRow.s1_x - egoPos.x
  const s1_rel_y = sctRow.s1_y - egoPos.y
  const s1_dy_local = -s1_rel_x * sin_h + s1_rel_y * cos_h
  const s1_offset = Math.abs(s1_dy_local)

  const [p2CanvasX, p2CanvasY] = rotateAndTransform(sctRow.p2_x, sctRow.p2_y)
  const [t2CanvasX, t2CanvasY] = rotateAndTransform(sctRow.t2_x, sctRow.t2_y)

  // S1オフセット分の終点
  const offsetEndX = sctRow.p2_x + unit_x * s1_offset
  const offsetEndY = sctRow.p2_y + unit_y * s1_offset
  const [offsetEndCanvasX, offsetEndCanvasY] = rotateAndTransform(offsetEndX, offsetEndY)

  // S1オフセット部分（薄い色）
  ctx.save()
  ctx.strokeStyle = 'rgba(34, 139, 34, 0.3)'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.moveTo(p2CanvasX, p2CanvasY)
  ctx.lineTo(offsetEndCanvasX, offsetEndCanvasY)
  ctx.stroke()
  ctx.restore()

  // 実際のdy距離部分（濃い色）
  ctx.save()
  ctx.strokeStyle = 'rgba(34, 139, 34, 0.9)'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.moveTo(offsetEndCanvasX, offsetEndCanvasY)
  ctx.lineTo(t2CanvasX, t2CanvasY)
  ctx.stroke()
  ctx.restore()

  // DYラベル
  const dyMidCanvasX = (offsetEndCanvasX + t2CanvasX) / 2
  const dyMidCanvasY = (offsetEndCanvasY + t2CanvasY) / 2
  ctx.save()
  ctx.fillStyle = 'rgba(255, 255, 255, 1.0)'
  ctx.font = 'bold 14px Arial'
  ctx.textAlign = 'center'
  ctx.fillText(`dy: ${Math.abs(dy).toFixed(1)}m`, dyMidCanvasX, dyMidCanvasY - 10)
  ctx.restore()

  // offsetEnd点
  ctx.save()
  ctx.beginPath()
  ctx.arc(offsetEndCanvasX, offsetEndCanvasY, 5, 0, 2 * Math.PI)
  ctx.fillStyle = '#90EE90'
  ctx.fill()
  ctx.strokeStyle = '#000000'
  ctx.lineWidth = 1
  ctx.stroke()
  ctx.restore()
}

/** 入れ替えモード時の対象車両側DX線を描画 */
function drawSwapModeDXLine(
  drawCtx: ReferencePointDrawContext,
  sctRow: SCTRow,
  targetPos: VehiclePosition
) {
  const { ctx, rotateAndTransform, getVehicleBBox } = drawCtx
  const dx = sctRow.dx
  if (dx === null || dx === undefined || dx <= 0) return
  if (sctRow.p1_x === undefined || sctRow.p1_y === undefined || isNaN(sctRow.p1_x) || isNaN(sctRow.p1_y)) return

  const targetBbox = getVehicleBBox(targetPos.vehicleId)
  const targetRearOffsetX = (targetBbox?.Center.x || 0) - (targetBbox?.Dimensions.length || 0) / 2
  const targetRearX = targetPos.x + targetRearOffsetX * Math.cos(targetPos.heading)
  const targetRearY = targetPos.y + targetRearOffsetX * Math.sin(targetPos.heading)

  const [rearCanvasX, rearCanvasY] = rotateAndTransform(targetRearX, targetRearY)
  const [p1CanvasX, p1CanvasY] = rotateAndTransform(sctRow.p1_x, sctRow.p1_y)

  ctx.save()
  ctx.strokeStyle = 'rgba(255, 69, 0, 0.9)'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.moveTo(rearCanvasX, rearCanvasY)
  ctx.lineTo(p1CanvasX, p1CanvasY)
  ctx.stroke()
  ctx.restore()

  // DXラベル
  const midCanvasX = (rearCanvasX + p1CanvasX) / 2
  const midCanvasY = (rearCanvasY + p1CanvasY) / 2
  ctx.save()
  ctx.fillStyle = 'rgba(255, 255, 255, 1.0)'
  ctx.font = 'bold 14px Arial'
  ctx.textAlign = 'center'
  ctx.fillText(`dx: ${Math.abs(dx).toFixed(1)}m`, midCanvasX, midCanvasY - 10)
  ctx.restore()
}

// ---------------------------------------------------------------------------
// 公開API
// ---------------------------------------------------------------------------

/** 全参照点を描画するメインエントリポイント */
export function drawReferencePoints(
  drawCtx: ReferencePointDrawContext,
  egoTrajectory: VehiclePosition[] | null,
  targetTrajectories: VehiclePosition[][],
  currentTime: number,
  sctDatasets: SCTDataset[],
  selectedDatasetIndex: number,
  showReferencePoints: boolean,
  scbDisplayMode: SCBDisplayMode,
  swapSCBAxes: boolean
) {
  if (sctDatasets.length === 0 || selectedDatasetIndex >= sctDatasets.length) return

  const sctDataset = sctDatasets[selectedDatasetIndex]
  const egoPos = egoTrajectory ? findPositionAtTime(egoTrajectory, currentTime) : null

  if (!egoPos || !sctDataset || !egoTrajectory) return

  const frameIndex = findFrameIndexAtTime(egoTrajectory, currentTime)
  const sctRow = sctDataset.data.find((row: SCTRow) => row.frame === frameIndex)

  if (!sctRow || sctRow.dy === null || sctRow.dy === undefined) return

  const dx = sctRow.dx
  const dy = sctRow.dy

  // P6仕様の計算参照点マーカー
  if (showReferencePoints) {
    drawReferenceMarkers(drawCtx, sctRow, egoPos)
  }

  // T1マーカー（最前面）
  if (showReferencePoints) {
    drawT1Marker(drawCtx, sctRow)
  }

  // 自車両の4頂点マーカー
  if (showReferencePoints) {
    drawVehicleVertexMarkers(drawCtx, egoPos, 'rgba(255, 255, 0, 0.9)')
  }

  // DX可視化線
  const skipEgoDxLine = swapSCBAxes && scbDisplayMode === 'position-based' && (dx ?? 0) > 0
  if (showReferencePoints && !skipEgoDxLine) {
    drawDXVisualization(drawCtx, sctRow, egoPos, egoTrajectory, currentTime)
  }

  // DY可視化線
  if (showReferencePoints) {
    drawDYVisualization(drawCtx, sctRow, egoPos, dy)
  }

  // 対象車両の頂点マーカー
  const targetTrajectory = targetTrajectories.find(traj =>
    traj.length > 0 && traj[0].vehicleId === sctDataset.targetVehicleId
  )
  if (showReferencePoints && targetTrajectory && egoTrajectory) {
    const targetPos = findPositionAtTime(targetTrajectory, currentTime)
    if (targetPos) {
      drawVehicleVertexMarkers(drawCtx, targetPos, 'rgba(0, 255, 255, 0.9)')
    }
  }

  // 入れ替えモード時の対象車両側DX線
  if (swapSCBAxes && scbDisplayMode === 'position-based') {
    if (targetTrajectory) {
      const targetPos = findPositionAtTime(targetTrajectory, currentTime)
      if (targetPos && showReferencePoints) {
        drawSwapModeDXLine(drawCtx, sctRow, targetPos)
      }
    }
  }
}
