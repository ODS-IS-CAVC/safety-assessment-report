import { VehiclePosition, VehicleBBoxConfig, SCTDataset } from '../types'
import { SCBDisplayMode } from '../components/RenderingControls'
import {
  VEHICLE_OUTER_STROKE_COLOR,
  VEHICLE_INNER_STROKE_COLOR,
  EGO_VEHICLE_COLOR,
  TARGET_VEHICLE_COLORS,
  EGO_TRAJECTORY_COLOR_PAST,
  EGO_TRAJECTORY_COLOR_FUTURE,
  TARGET_TRAJECTORY_COLORS_PAST,
  TARGET_TRAJECTORY_COLORS_FUTURE,
} from './renderConstants'
import {
  findPositionAtTime,
  drawTrajectoryLine,
} from './trajectoryRenderer'
import { SCBDrawContext } from './scbRenderer'
import { orchestrateSCBDrawing } from './scbOrchestrator'
import { drawVehicleCenterMarkers, drawReferencePoints } from './referencePointRenderer'

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

/** renderVehiclesのパラメータ */
export interface RenderVehiclesParams {
  ctx: CanvasRenderingContext2D
  canvasWidth: number
  canvasHeight: number
  egoTrajectory: VehiclePosition[] | null
  targetTrajectories: VehiclePosition[][]
  currentTime: number
  zoom: number
  offsetX: number
  offsetY: number
  trajectoryRotation: number
  boundingBox: { minX: number; minY: number; baseScale: number; margin: number } | null
  vehicleBBoxConfig: VehicleBBoxConfig | null
  sctDatasets: SCTDataset[]
  selectedDatasetIndex: number
  showVehicleNames: boolean
  showReferencePoints: boolean
  scbDisplayMode: SCBDisplayMode
  swapSCBAxes: boolean
}

// ---------------------------------------------------------------------------
// 内部ヘルパー
// ---------------------------------------------------------------------------

/** 車両名からバウンディングボックス情報を取得 */
function getVehicleBBox(vehicleBBoxConfig: VehicleBBoxConfig | null, vehicleId: string) {
  if (!vehicleBBoxConfig) return null

  let cleanId = vehicleId
  if (cleanId.startsWith('Veh_')) {
    cleanId = cleanId.substring(4)
  }
  const vehicleName = cleanId.split('_')[0]
  const vehicleData = vehicleBBoxConfig.vehicles.find(v => v.name === vehicleName)
  return vehicleData?.BoundingBox || null
}

/** 座標変換関数を生成 */
function createRotateAndTransform(
  canvasWidth: number,
  canvasHeight: number,
  rotationRad: number,
  boundingBox: RenderVehiclesParams['boundingBox'],
  zoom: number,
  offsetX: number,
  offsetY: number
): (x: number, y: number) => [number, number] {
  const canvasCenterX = canvasWidth / 2
  const canvasCenterY = canvasHeight / 2

  return (x: number, y: number): [number, number] => {
    const rotatedX = x * Math.cos(rotationRad) - y * Math.sin(rotationRad)
    const rotatedY = x * Math.sin(rotationRad) + y * Math.cos(rotationRad)

    if (boundingBox) {
      const { minX, minY, baseScale, margin } = boundingBox
      const baseX = ((rotatedX - minX) * baseScale) + margin
      const baseY = canvasHeight - (((rotatedY - minY) * baseScale) + margin)
      const relativeX = baseX - canvasCenterX
      const relativeY = baseY - canvasCenterY
      const zoomedX = relativeX * zoom
      const zoomedY = relativeY * zoom
      return [zoomedX + offsetX + canvasCenterX, zoomedY + offsetY + canvasCenterY]
    }

    const canvasX = rotatedX * zoom + offsetX + canvasCenterX
    const canvasY = -rotatedY * zoom + offsetY + canvasCenterY
    return [canvasX, canvasY]
  }
}

// ---------------------------------------------------------------------------
// 公開API
// ---------------------------------------------------------------------------

/** 車両の描画（後方互換シグネチャ） */
export function renderVehicles(
  ctx: CanvasRenderingContext2D,
  canvasWidth: number,
  canvasHeight: number,
  egoTrajectory: VehiclePosition[] | null,
  targetTrajectories: VehiclePosition[][],
  currentTime: number,
  zoom: number,
  offsetX: number,
  offsetY: number,
  trajectoryRotation: number,
  boundingBox: { minX: number; minY: number; baseScale: number; margin: number } | null,
  vehicleBBoxConfig: VehicleBBoxConfig | null,
  sctDatasets: SCTDataset[],
  selectedDatasetIndex: number,
  showVehicleNames: boolean,
  showReferencePoints: boolean,
  scbDisplayMode: SCBDisplayMode,
  swapSCBAxes: boolean = false
) {
  renderVehiclesImpl({
    ctx, canvasWidth, canvasHeight,
    egoTrajectory, targetTrajectories, currentTime,
    zoom, offsetX, offsetY, trajectoryRotation,
    boundingBox, vehicleBBoxConfig,
    sctDatasets, selectedDatasetIndex,
    showVehicleNames, showReferencePoints,
    scbDisplayMode, swapSCBAxes
  })
}

/** 車両の描画（実装） */
function renderVehiclesImpl(params: RenderVehiclesParams) {
  const {
    ctx, canvasWidth, canvasHeight,
    egoTrajectory, targetTrajectories, currentTime,
    zoom, offsetX, offsetY, trajectoryRotation,
    boundingBox, vehicleBBoxConfig,
    sctDatasets, selectedDatasetIndex,
    showVehicleNames, showReferencePoints,
    scbDisplayMode, swapSCBAxes
  } = params

  const rotationRad = (trajectoryRotation * Math.PI) / 180
  const rotateAndTransform = createRotateAndTransform(canvasWidth, canvasHeight, rotationRad, boundingBox, zoom, offsetX, offsetY)
  const getVehicleBBoxFn = (vehicleId: string) => getVehicleBBox(vehicleBBoxConfig, vehicleId)

  // 軌跡線の太さ
  const trajectoryWidth = 0.5 * zoom * (boundingBox?.baseScale || 1)

  // 車両を四角形で描画する内部関数
  const drawVehicleRectangle = (
    x: number, y: number, heading: number, color: string, label: string, vehicleId: string
  ) => {
    const bbox = getVehicleBBoxFn(vehicleId)
    const length = bbox ? bbox.Dimensions.length : 4.5
    const width = bbox ? bbox.Dimensions.width : 1.8
    const centerOffsetX = bbox ? bbox.Center.x : 0

    const [canvasX, canvasY] = rotateAndTransform(x, y)
    const scale = zoom * (boundingBox?.baseScale || 1)
    const scaledLength = length * scale
    const scaledWidth = width * scale
    const scaledCenterOffset = centerOffsetX * scale

    ctx.save()
    ctx.translate(canvasX, canvasY)
    ctx.rotate(-heading - rotationRad)

    // 車両本体
    ctx.fillStyle = color
    ctx.fillRect(-scaledLength / 2 + scaledCenterOffset, -scaledWidth / 2, scaledLength, scaledWidth)

    // 枠線
    const outerLineWidth = Math.max(0.10 * width * scale, 1.5)
    const innerLineWidth = Math.max(0.05 * width * scale, 0.5)

    if (color === EGO_VEHICLE_COLOR) {
      ctx.strokeStyle = VEHICLE_OUTER_STROKE_COLOR
      ctx.lineWidth = outerLineWidth
      ctx.strokeRect(-scaledLength / 2 + scaledCenterOffset, -scaledWidth / 2, scaledLength, scaledWidth)
    }

    ctx.strokeStyle = VEHICLE_INNER_STROKE_COLOR
    ctx.lineWidth = innerLineWidth
    ctx.strokeRect(-scaledLength / 2 + scaledCenterOffset, -scaledWidth / 2, scaledLength, scaledWidth)

    // 前方向を示す線
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = Math.max(0.03 * width * scale, 0.3)
    ctx.beginPath()
    ctx.moveTo(0, 0)
    ctx.lineTo(scaledLength / 2 + scaledCenterOffset, 0)
    ctx.stroke()

    ctx.restore()

    // ラベル表示
    if (showVehicleNames && zoom > 0.5) {
      ctx.fillStyle = '#ffffff'
      ctx.font = `${Math.min(12 * zoom, 16)}px Arial`
      ctx.textAlign = 'center'
      ctx.fillText(label, canvasX, canvasY - scaledWidth / 2 - 5)
    }
  }

  // --- 描画順序: 軌跡 → SCB → 車両本体 → 参照点 ---

  // 1. 軌跡線を描画
  if (egoTrajectory) {
    drawTrajectoryLine(ctx, egoTrajectory, currentTime, EGO_TRAJECTORY_COLOR_PAST, EGO_TRAJECTORY_COLOR_FUTURE, rotateAndTransform, trajectoryWidth)
  }
  targetTrajectories.forEach((trajectory, index) => {
    drawTrajectoryLine(
      ctx, trajectory, currentTime,
      TARGET_TRAJECTORY_COLORS_PAST[index % TARGET_TRAJECTORY_COLORS_PAST.length],
      TARGET_TRAJECTORY_COLORS_FUTURE[index % TARGET_TRAJECTORY_COLORS_FUTURE.length],
      rotateAndTransform, trajectoryWidth
    )
  })

  // 2. SCB領域を描画（全モード対応）
  const drawCtx: SCBDrawContext = {
    ctx, zoom, rotationRad, boundingBox,
    rotateAndTransform, getVehicleBBox: getVehicleBBoxFn
  }

  orchestrateSCBDrawing(
    drawCtx, egoTrajectory, targetTrajectories, currentTime,
    sctDatasets, selectedDatasetIndex, scbDisplayMode, swapSCBAxes
  )

  // 3. 車両本体を最前面に描画
  if (egoTrajectory) {
    const egoPos = findPositionAtTime(egoTrajectory, currentTime)
    if (egoPos) {
      drawVehicleRectangle(egoPos.x, egoPos.y, egoPos.heading, EGO_VEHICLE_COLOR, egoPos.vehicleId, egoPos.vehicleId)
    }
  }
  targetTrajectories.forEach((trajectory, index) => {
    const targetPos = findPositionAtTime(trajectory, currentTime)
    if (targetPos) {
      const color = TARGET_VEHICLE_COLORS[index % TARGET_VEHICLE_COLORS.length]
      drawVehicleRectangle(targetPos.x, targetPos.y, targetPos.heading, color, targetPos.vehicleId, targetPos.vehicleId)
    }
  })

  // 4. 車両中心マーカー
  drawVehicleCenterMarkers(ctx, egoTrajectory, targetTrajectories, currentTime, rotateAndTransform)

  // 5. 参照点（DX/DY可視化、S1/T1/P1/P2/T2マーカー）
  const refDrawCtx = { ctx, rotateAndTransform, getVehicleBBox: getVehicleBBoxFn }
  drawReferencePoints(
    refDrawCtx, egoTrajectory, targetTrajectories, currentTime,
    sctDatasets, selectedDatasetIndex, showReferencePoints,
    scbDisplayMode, swapSCBAxes
  )
}
