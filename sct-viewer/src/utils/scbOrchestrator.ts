import { VehiclePosition, SCTDataset, SCTRow } from '../types'
import { SCBDisplayMode } from '../components/RenderingControls'
import {
  SCBDrawContext,
  VehicleSCBPolygons,
  drawLongitudinalSCBRegions,
  drawLateralSCBRegions,
  drawDebugCollisionPolygons,
  drawCollisionPolygon,
} from './scbRenderer'
import {
  checkSCBCollisionsWithPolygons,
  createVehicleOBBPolygon,
  createSCBPolygon,
  type SCBOverlapResult
} from './scbUtils'
import { findPositionAtTime, findFrameIndexAtTime } from './trajectoryRenderer'

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

/** 衝突しているSCB情報 */
interface CollidingSCBInfo {
  vehiclePos: VehiclePosition
  egoPos: VehiclePosition
  p2_x?: number
  p2_y?: number
  t2_x?: number
  t2_y?: number
  s1_x?: number
  s1_y?: number
  sdx?: number
  scb1x?: number
  scb2x?: number
  scb3x?: number
  sdy?: number
  scb1y?: number
  scb2y?: number
  scb3y?: number
  direction: 'forward' | 'backward'
  overlapLevel: number
  overlapResult: SCBOverlapResult
  isEgo: boolean
}

/** SCBオーケストレーション結果 */
export interface SCBOrchestrationResult {
  overlapLevel: number | undefined
  targetVehicleId: string | undefined
}

// ---------------------------------------------------------------------------
// 内部ヘルパー
// ---------------------------------------------------------------------------

/** 初期overlapResultを作成 */
function createInitialOverlapResult(): SCBOverlapResult {
  return {
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
}

/** 車両本体のポリゴンペアを作成 */
function createBodyPolygons(
  egoPos: VehiclePosition,
  targetPos: VehiclePosition,
  getVehicleBBox: SCBDrawContext['getVehicleBBox']
): { egoPolygons: VehicleSCBPolygons; targetPolygons: VehicleSCBPolygons } {
  const egoPolygons: VehicleSCBPolygons = { body: null, scb0: null, scb1: null, scb2: null, scb3: null }
  const targetPolygons: VehicleSCBPolygons = { body: null, scb0: null, scb1: null, scb2: null, scb3: null }

  const egoBbox = getVehicleBBox(egoPos.vehicleId)
  const targetBbox = getVehicleBBox(targetPos.vehicleId)

  if (egoBbox) {
    egoPolygons.body = createVehicleOBBPolygon(
      egoPos.x, egoPos.y, egoPos.heading,
      egoBbox.Dimensions.length, egoBbox.Dimensions.width, egoBbox.Center.x
    )
  }
  if (targetBbox) {
    targetPolygons.body = createVehicleOBBPolygon(
      targetPos.x, targetPos.y, targetPos.heading,
      targetBbox.Dimensions.length, targetBbox.Dimensions.width, targetBbox.Center.x
    )
  }
  return { egoPolygons, targetPolygons }
}

/** SCBの表示条件を判定 */
function checkSCBVisibility(sctRow: SCTRow): { shouldShowSCBX: boolean; shouldShowSCBY: boolean } {
  const isApproachingX = sctRow.dx != null && sctRow.vx_ma != null && sctRow.dx * sctRow.vx_ma > 0
  const isApproachingY = sctRow.dy != null && sctRow.vy_ma != null && sctRow.dy * sctRow.vy_ma > 0

  const shouldShowSCBX = isApproachingX &&
    sctRow.scb1x != null && sctRow.scb2x != null && sctRow.scb3x != null &&
    sctRow.sctx != null && sctRow.sctx > 0 && sctRow.sctx <= 8

  const shouldShowSCBY = isApproachingY &&
    sctRow.scb1y != null && sctRow.scb2y != null && sctRow.scb3y != null &&
    sctRow.scty != null && sctRow.scty > 0 && sctRow.scty <= 8

  return { shouldShowSCBX, shouldShowSCBY }
}

/** collidingSCBInfoを作成するヘルパー */
function buildCollidingSCBInfo(
  vehiclePos: VehiclePosition,
  egoPos: VehiclePosition,
  sctRow: SCTRow,
  type: 'longitudinal' | 'lateral',
  direction: 'forward' | 'backward',
  overlapResult: SCBOverlapResult,
  isEgo: boolean
): CollidingSCBInfo {
  if (type === 'longitudinal') {
    return {
      vehiclePos, egoPos,
      sdx: sctRow.sdx ?? undefined,
      scb1x: sctRow.scb1x ?? undefined,
      scb2x: sctRow.scb2x ?? undefined,
      scb3x: sctRow.scb3x ?? undefined,
      direction,
      overlapLevel: overlapResult.level,
      overlapResult,
      isEgo
    }
  }
  return {
    vehiclePos, egoPos,
    p2_x: sctRow.p2_x ?? undefined,
    p2_y: sctRow.p2_y ?? undefined,
    t2_x: sctRow.t2_x ?? undefined,
    t2_y: sctRow.t2_y ?? undefined,
    s1_x: sctRow.s1_x ?? undefined,
    s1_y: sctRow.s1_y ?? undefined,
    sdy: sctRow.sdy ?? undefined,
    scb1y: sctRow.scb1y ?? undefined,
    scb2y: sctRow.scb2y ?? undefined,
    scb3y: sctRow.scb3y ?? undefined,
    direction,
    overlapLevel: overlapResult.level,
    overlapResult,
    isEgo
  }
}

// ---------------------------------------------------------------------------
// 表示モード別の描画ストラテジー
// ---------------------------------------------------------------------------

/** vehicle-basedモード: 自車に前後のSCB、対象車に横方向のSCB */
function renderVehicleBasedMode(
  drawCtx: SCBDrawContext,
  egoPos: VehiclePosition,
  targetPos: VehiclePosition,
  sctRow: SCTRow,
  shouldShowSCBX: boolean,
  shouldShowSCBY: boolean,
  collidingSCBInfoList: CollidingSCBInfo[]
): { overlapResult: SCBOverlapResult } {
  const dx = sctRow.dx ?? 0
  const direction: 'forward' | 'backward' = dx > 0 ? 'forward' : 'backward'
  let overlapResult = createInitialOverlapResult()

  const { egoPolygons, targetPolygons } = createBodyPolygons(egoPos, targetPos, drawCtx.getVehicleBBox)

  // 縦方向SCB（X軸）- 自車に表示
  if (shouldShowSCBX) {
    const scbPolygons = drawLongitudinalSCBRegions(drawCtx, egoPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, direction, undefined, undefined, false)
    egoPolygons.scb0 = scbPolygons.scb0
    egoPolygons.scb1 = scbPolygons.scb1
    egoPolygons.scb2 = scbPolygons.scb2
    egoPolygons.scb3 = scbPolygons.scb3

    collidingSCBInfoList.push(buildCollidingSCBInfo(egoPos, egoPos, sctRow, 'longitudinal', direction, overlapResult, true))
  }

  // 横方向SCB（Y軸）- 対象車に表示
  if (shouldShowSCBY) {
    const scbPolygons = drawLateralSCBRegions(drawCtx, targetPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, undefined, undefined, false)
    targetPolygons.scb0 = scbPolygons.scb0
    targetPolygons.scb1 = scbPolygons.scb1
    targetPolygons.scb2 = scbPolygons.scb2
    targetPolygons.scb3 = scbPolygons.scb3

    collidingSCBInfoList.push(buildCollidingSCBInfo(targetPos, egoPos, sctRow, 'lateral', direction, overlapResult, false))
  }

  // ポリゴン同士で衝突判定
  overlapResult = checkSCBCollisionsWithPolygons(egoPolygons, targetPolygons)
  drawDebugCollisionPolygons(drawCtx.ctx, egoPolygons, targetPolygons, drawCtx.rotateAndTransform)

  // 衝突判定結果を使って再描画
  if (overlapResult.level < 4) {
    if (shouldShowSCBX) {
      drawLongitudinalSCBRegions(drawCtx, egoPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, direction, overlapResult.level, overlapResult)
    }
    if (shouldShowSCBY) {
      drawLateralSCBRegions(drawCtx, targetPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, overlapResult.level, overlapResult)
    }
  }

  // collidingSCBInfoListのoverlapResultを更新
  collidingSCBInfoList.forEach(info => {
    info.overlapResult = overlapResult
    info.overlapLevel = overlapResult.level
  })

  return { overlapResult }
}

/** position-basedモード（通常）: 後方車両に縦方向SCB、前方車両に横方向SCB */
function renderPositionBasedNormal(
  drawCtx: SCBDrawContext,
  egoPos: VehiclePosition,
  targetPos: VehiclePosition,
  sctRow: SCTRow,
  shouldShowSCBX: boolean,
  shouldShowSCBY: boolean,
  collidingSCBInfoList: CollidingSCBInfo[]
): { overlapResult: SCBOverlapResult } {
  const dx = sctRow.dx ?? 0
  let overlapResult = createInitialOverlapResult()

  if (dx > 0) {
    // dx > 0: 対象車が前方、自車が後方
    const { egoPolygons, targetPolygons } = createBodyPolygons(egoPos, targetPos, drawCtx.getVehicleBBox)

    if (shouldShowSCBX) {
      const scbPolygons = drawLongitudinalSCBRegions(drawCtx, egoPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'forward', undefined, undefined, false)
      egoPolygons.scb0 = scbPolygons.scb0
      egoPolygons.scb1 = scbPolygons.scb1
      egoPolygons.scb2 = scbPolygons.scb2
      egoPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(egoPos, egoPos, sctRow, 'longitudinal', 'forward', overlapResult, true))
    }
    if (shouldShowSCBY) {
      const scbPolygons = drawLateralSCBRegions(drawCtx, targetPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, undefined, undefined, false)
      targetPolygons.scb0 = scbPolygons.scb0
      targetPolygons.scb1 = scbPolygons.scb1
      targetPolygons.scb2 = scbPolygons.scb2
      targetPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(targetPos, egoPos, sctRow, 'lateral', 'forward', overlapResult, false))
    }

    overlapResult = checkSCBCollisionsWithPolygons(egoPolygons, targetPolygons)
    drawDebugCollisionPolygons(drawCtx.ctx, egoPolygons, targetPolygons, drawCtx.rotateAndTransform)

    if (overlapResult.level < 4) {
      if (shouldShowSCBX) drawLongitudinalSCBRegions(drawCtx, egoPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'forward', overlapResult.level, overlapResult)
      if (shouldShowSCBY) drawLateralSCBRegions(drawCtx, targetPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, overlapResult.level, overlapResult)
    }
  } else if (dx < 0) {
    // dx < 0: 対象車が後方、自車が前方
    const { egoPolygons, targetPolygons } = createBodyPolygons(egoPos, targetPos, drawCtx.getVehicleBBox)

    if (shouldShowSCBX) {
      // 後方車両（対象車）に縦方向SCB
      const scbPolygons = drawLongitudinalSCBRegions(drawCtx, targetPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'forward', undefined, undefined, false)
      targetPolygons.scb0 = scbPolygons.scb0
      targetPolygons.scb1 = scbPolygons.scb1
      targetPolygons.scb2 = scbPolygons.scb2
      targetPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(targetPos, egoPos, sctRow, 'longitudinal', 'forward', overlapResult, false))
    }
    if (shouldShowSCBY) {
      // 前方車両（自車）に横方向SCB
      const scbPolygons = drawLateralSCBRegions(drawCtx, egoPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, undefined, undefined, false)
      egoPolygons.scb0 = scbPolygons.scb0
      egoPolygons.scb1 = scbPolygons.scb1
      egoPolygons.scb2 = scbPolygons.scb2
      egoPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(egoPos, egoPos, sctRow, 'lateral', 'forward', overlapResult, true))
    }

    overlapResult = checkSCBCollisionsWithPolygons(egoPolygons, targetPolygons)
    drawDebugCollisionPolygons(drawCtx.ctx, egoPolygons, targetPolygons, drawCtx.rotateAndTransform)

    if (overlapResult.level < 4) {
      if (shouldShowSCBX) drawLongitudinalSCBRegions(drawCtx, targetPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'forward', overlapResult.level, overlapResult, undefined, true)
      if (shouldShowSCBY) drawLateralSCBRegions(drawCtx, egoPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, overlapResult.level, overlapResult, undefined, true)
    }
  }

  collidingSCBInfoList.forEach(info => {
    info.overlapResult = overlapResult
    info.overlapLevel = overlapResult.level
  })

  return { overlapResult }
}

/** position-basedモード（入れ替え）: 後方車両に横方向SCB、前方車両に縦方向SCB */
function renderPositionBasedSwapped(
  drawCtx: SCBDrawContext,
  egoPos: VehiclePosition,
  targetPos: VehiclePosition,
  sctRow: SCTRow,
  shouldShowSCBX: boolean,
  shouldShowSCBY: boolean,
  collidingSCBInfoList: CollidingSCBInfo[]
): { overlapResult: SCBOverlapResult } {
  const dx = sctRow.dx ?? 0
  let overlapResult = createInitialOverlapResult()

  if (dx > 0) {
    // dx > 0: 対象車が前方、自車が後方
    const { egoPolygons, targetPolygons } = createBodyPolygons(egoPos, targetPos, drawCtx.getVehicleBBox)

    // 入れ替え: 後方（自車）に横方向SCB、前方（対象車）に縦方向SCB
    if (shouldShowSCBX) {
      const scbPolygons = drawLateralSCBRegions(drawCtx, egoPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, undefined, undefined, false)
      targetPolygons.scb0 = scbPolygons.scb0
      targetPolygons.scb1 = scbPolygons.scb1
      targetPolygons.scb2 = scbPolygons.scb2
      targetPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(egoPos, egoPos, sctRow, 'lateral', 'forward', overlapResult, true))
    }
    if (shouldShowSCBY) {
      const scbPolygons = drawLongitudinalSCBRegions(drawCtx, targetPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'backward', undefined, undefined, false)
      egoPolygons.scb0 = scbPolygons.scb0
      egoPolygons.scb1 = scbPolygons.scb1
      egoPolygons.scb2 = scbPolygons.scb2
      egoPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(targetPos, egoPos, sctRow, 'longitudinal', 'backward', overlapResult, false))
    }

    overlapResult = checkSCBCollisionsWithPolygons(egoPolygons, targetPolygons)
    drawDebugCollisionPolygons(drawCtx.ctx, egoPolygons, targetPolygons, drawCtx.rotateAndTransform)

    if (overlapResult.level < 4) {
      if (shouldShowSCBX) drawLateralSCBRegions(drawCtx, egoPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, overlapResult.level, overlapResult, undefined, true)
      if (shouldShowSCBY) drawLongitudinalSCBRegions(drawCtx, targetPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'backward', overlapResult.level, overlapResult, undefined, true)
    }
  } else if (dx < 0) {
    // dx < 0: 対象車が後方、自車が前方
    const { egoPolygons, targetPolygons } = createBodyPolygons(egoPos, targetPos, drawCtx.getVehicleBBox)

    // 入れ替え: 自車（前方）に縦方向SCB（後方へ）、対象車（後方）に横方向SCB
    if (shouldShowSCBY) {
      const scbPolygons = drawLongitudinalSCBRegions(drawCtx, egoPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'backward', undefined, undefined, false)
      targetPolygons.scb0 = scbPolygons.scb0
      targetPolygons.scb1 = scbPolygons.scb1
      targetPolygons.scb2 = scbPolygons.scb2
      targetPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(egoPos, egoPos, sctRow, 'longitudinal', 'backward', overlapResult, true))
    }
    if (shouldShowSCBX) {
      const scbPolygons = drawLateralSCBRegions(drawCtx, targetPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, undefined, undefined, false)
      egoPolygons.scb0 = scbPolygons.scb0
      egoPolygons.scb1 = scbPolygons.scb1
      egoPolygons.scb2 = scbPolygons.scb2
      egoPolygons.scb3 = scbPolygons.scb3
      collidingSCBInfoList.push(buildCollidingSCBInfo(targetPos, egoPos, sctRow, 'lateral', 'forward', overlapResult, false))
    }

    overlapResult = checkSCBCollisionsWithPolygons(egoPolygons, targetPolygons)
    drawDebugCollisionPolygons(drawCtx.ctx, egoPolygons, targetPolygons, drawCtx.rotateAndTransform)

    if (overlapResult.level < 4) {
      if (shouldShowSCBX) drawLateralSCBRegions(drawCtx, targetPos, egoPos, sctRow.t2_x, sctRow.t2_y, sctRow.sdy, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, overlapResult.level, overlapResult, undefined, true)
      if (shouldShowSCBY) drawLongitudinalSCBRegions(drawCtx, egoPos, sctRow.sdx, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x, 'backward', overlapResult.level, overlapResult, undefined, true)
    }
  }

  collidingSCBInfoList.forEach(info => {
    info.overlapResult = overlapResult
    info.overlapLevel = overlapResult.level
  })

  return { overlapResult }
}

// ---------------------------------------------------------------------------
// 衝突ポリゴン描画
// ---------------------------------------------------------------------------

/** collidingSCBInfoListを使って衝突判定ポリゴンを描画 */
function drawCollisionPolygons(
  ctx: CanvasRenderingContext2D,
  collidingSCBInfoList: CollidingSCBInfo[],
  getVehicleBBox: SCBDrawContext['getVehicleBBox'],
  rotateAndTransform: (x: number, y: number) => [number, number]
) {
  collidingSCBInfoList.forEach((info) => {
    const vehicleBbox = getVehicleBBox(info.vehiclePos.vehicleId)
    if (!vehicleBbox) return

    const len = vehicleBbox.Dimensions.length
    const wid = vehicleBbox.Dimensions.width
    const cx = vehicleBbox.Center.x

    // 縦方向SCBの衝突判定ポリゴン
    if (info.sdx !== undefined) {
      const p = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.vehiclePos.heading, len, wid, cx, info.sdx, info.direction)
      if (p) drawCollisionPolygon(ctx, p, 'rgb(128, 128, 128)', rotateAndTransform)
    }
    if (info.scb1x !== undefined && info.scb2x !== undefined && info.scb3x !== undefined) {
      const p1 = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.vehiclePos.heading, len, wid, cx, info.scb1x, info.direction)
      if (p1) drawCollisionPolygon(ctx, p1, 'rgb(255, 140, 0)', rotateAndTransform)
      const p2 = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.vehiclePos.heading, len, wid, cx, info.scb2x, info.direction)
      if (p2) drawCollisionPolygon(ctx, p2, 'rgb(255, 215, 0)', rotateAndTransform)
      const p3 = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.vehiclePos.heading, len, wid, cx, info.scb3x, info.direction)
      if (p3) drawCollisionPolygon(ctx, p3, 'rgb(0, 191, 255)', rotateAndTransform)
    }

    // 横方向SCBの衝突判定ポリゴン
    let t2OffsetY = 0
    if (info.t2_x != null && info.t2_y != null && !isNaN(info.t2_x) && !isNaN(info.t2_y)) {
      const dx_t2 = info.t2_x - info.vehiclePos.x
      const dy_t2 = info.t2_y - info.vehiclePos.y
      const cos_ego = Math.cos(info.egoPos.heading)
      const sin_ego = Math.sin(info.egoPos.heading)
      t2OffsetY = dx_t2 * sin_ego - dy_t2 * cos_ego
    }
    const scbDirection = t2OffsetY > 0 ? 'right' : 'left'

    if (info.sdy !== undefined) {
      const p = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.egoPos.heading, len, wid, cx, info.sdy, scbDirection)
      if (p) drawCollisionPolygon(ctx, p, 'rgb(128, 128, 128)', rotateAndTransform)
    }
    if (info.scb1y !== undefined && info.scb2y !== undefined && info.scb3y !== undefined) {
      const p1 = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.egoPos.heading, len, wid, cx, info.scb1y, scbDirection)
      if (p1) drawCollisionPolygon(ctx, p1, 'rgb(255, 69, 0)', rotateAndTransform)
      const p2 = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.egoPos.heading, len, wid, cx, info.scb2y, scbDirection)
      if (p2) drawCollisionPolygon(ctx, p2, 'rgb(255, 215, 0)', rotateAndTransform)
      const p3 = createSCBPolygon(info.vehiclePos.x, info.vehiclePos.y, info.egoPos.heading, len, wid, cx, info.scb3y, scbDirection)
      if (p3) drawCollisionPolygon(ctx, p3, 'rgb(0, 191, 255)', rotateAndTransform)
    }
  })
}

/** 衝突しているSCBの表示用矩形を最前面に描画 */
function drawCollidingSCBFrontLayer(
  drawCtx: SCBDrawContext,
  collidingSCBInfoList: CollidingSCBInfo[]
) {
  collidingSCBInfoList.forEach((info) => {
    if (info.scb1x !== undefined || info.scb1y !== undefined) {
      if (info.scb1x !== undefined) {
        drawLongitudinalSCBRegions(
          drawCtx, info.vehiclePos,
          info.sdx, info.scb1x, info.scb2x, info.scb3x,
          info.direction, info.overlapLevel, info.overlapResult, true
        )
      }
      if (info.scb1y !== undefined) {
        drawLateralSCBRegions(
          drawCtx, info.vehiclePos, info.egoPos,
          info.t2_x, info.t2_y,
          info.sdy, info.scb1y, info.scb2y, info.scb3y,
          info.overlapLevel, info.overlapResult, true
        )
      }
    }
  })
}

// ---------------------------------------------------------------------------
// 公開API: SCBオーケストレーション
// ---------------------------------------------------------------------------

/** SCB描画全体をオーケストレーション */
export function orchestrateSCBDrawing(
  drawCtx: SCBDrawContext,
  egoTrajectory: VehiclePosition[] | null,
  targetTrajectories: VehiclePosition[][],
  currentTime: number,
  sctDatasets: SCTDataset[],
  selectedDatasetIndex: number,
  scbDisplayMode: SCBDisplayMode,
  swapSCBAxes: boolean
): SCBOrchestrationResult {
  let currentOverlapLevel: number | undefined = undefined
  let currentTargetVehicleId: string | undefined = undefined
  const collidingSCBInfoList: CollidingSCBInfo[] = []

  if (sctDatasets.length === 0 || selectedDatasetIndex >= sctDatasets.length) {
    return { overlapLevel: currentOverlapLevel, targetVehicleId: currentTargetVehicleId }
  }

  const sctDataset = sctDatasets[selectedDatasetIndex]
  const egoPos = egoTrajectory ? findPositionAtTime(egoTrajectory, currentTime) : null

  if (!egoPos || !sctDataset || !egoTrajectory) {
    return { overlapLevel: currentOverlapLevel, targetVehicleId: currentTargetVehicleId }
  }

  const frameIndex = findFrameIndexAtTime(egoTrajectory, currentTime)
  const sctRow = sctDataset.data.find((row: SCTRow) => row.frame === frameIndex)
  if (!sctRow) {
    return { overlapLevel: currentOverlapLevel, targetVehicleId: currentTargetVehicleId }
  }

  const targetTrajectory = targetTrajectories.find(traj =>
    traj.length > 0 && traj[0].vehicleId === sctDataset.targetVehicleId
  )
  if (!targetTrajectory) {
    return { overlapLevel: currentOverlapLevel, targetVehicleId: currentTargetVehicleId }
  }

  const targetPos = findPositionAtTime(targetTrajectory, currentTime)
  if (!targetPos) {
    return { overlapLevel: currentOverlapLevel, targetVehicleId: currentTargetVehicleId }
  }

  const { shouldShowSCBX, shouldShowSCBY } = checkSCBVisibility(sctRow)

  if (!shouldShowSCBX && !shouldShowSCBY) {
    return { overlapLevel: currentOverlapLevel, targetVehicleId: currentTargetVehicleId }
  }

  let result: { overlapResult: SCBOverlapResult }

  if (scbDisplayMode === 'vehicle-based') {
    result = renderVehicleBasedMode(drawCtx, egoPos, targetPos, sctRow, shouldShowSCBX, shouldShowSCBY, collidingSCBInfoList)
  } else if (!swapSCBAxes) {
    result = renderPositionBasedNormal(drawCtx, egoPos, targetPos, sctRow, shouldShowSCBX, shouldShowSCBY, collidingSCBInfoList)
  } else {
    result = renderPositionBasedSwapped(drawCtx, egoPos, targetPos, sctRow, shouldShowSCBX, shouldShowSCBY, collidingSCBInfoList)
  }

  currentOverlapLevel = result.overlapResult.level
  currentTargetVehicleId = targetPos.vehicleId

  // 衝突ポリゴン描画
  drawCollisionPolygons(drawCtx.ctx, collidingSCBInfoList, drawCtx.getVehicleBBox, drawCtx.rotateAndTransform)

  // 衝突しているSCBの表示用矩形を最前面に描画
  drawCollidingSCBFrontLayer(drawCtx, collidingSCBInfoList)

  return { overlapLevel: currentOverlapLevel, targetVehicleId: currentTargetVehicleId }
}
