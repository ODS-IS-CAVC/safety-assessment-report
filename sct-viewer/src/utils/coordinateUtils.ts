import { RoadNetworkData } from '../types/roadNetwork'
import { VehiclePosition } from '../types'

/** バウンディングボックスの範囲 */
export interface DataBounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

/** 描画用バウンディングボックス */
export interface BoundingBoxConfig {
  minX: number
  minY: number
  baseScale: number
  margin: number
}

/** OpenDRIVEの道路範囲を計算 */
export function calculateRoadBounds(roadNetworkData: RoadNetworkData): DataBounds {
  let minX = Infinity, maxX = -Infinity
  let minY = Infinity, maxY = -Infinity

  roadNetworkData.roads.forEach(road => {
    road.lanes.forEach(lane => {
      lane.points.forEach(point => {
        minX = Math.min(minX, point.x)
        maxX = Math.max(maxX, point.x)
        minY = Math.min(minY, point.y)
        maxY = Math.max(maxY, point.y)
      })
    })
  })

  return { minX, maxX, minY, maxY }
}

/** 軌跡の範囲を計算（回転考慮） */
export function calculateTrajectoryBounds(
  egoTrajectory: VehiclePosition[] | null,
  targetTrajectories: VehiclePosition[][],
  rotationRad: number
): DataBounds {
  let minX = Infinity, maxX = -Infinity
  let minY = Infinity, maxY = -Infinity

  const addTrajectoryPoints = (trajectory: VehiclePosition[]) => {
    trajectory.forEach(pos => {
      const rotatedX = pos.x * Math.cos(rotationRad) - pos.y * Math.sin(rotationRad)
      const rotatedY = pos.x * Math.sin(rotationRad) + pos.y * Math.cos(rotationRad)
      minX = Math.min(minX, rotatedX)
      maxX = Math.max(maxX, rotatedX)
      minY = Math.min(minY, rotatedY)
      maxY = Math.max(maxY, rotatedY)
    })
  }

  if (egoTrajectory) addTrajectoryPoints(egoTrajectory)
  targetTrajectories.forEach(addTrajectoryPoints)

  return { minX, maxX, minY, maxY }
}

/** データ範囲からバウンディングボックスを計算 */
export function calculateBoundingBox(
  canvasWidth: number,
  canvasHeight: number,
  bounds: DataBounds,
  margin: number = 50
): BoundingBoxConfig | null {
  if (!isFinite(bounds.minX) || !isFinite(bounds.maxX) || !isFinite(bounds.minY) || !isFinite(bounds.maxY)) {
    return null
  }

  const dataWidth = bounds.maxX - bounds.minX
  const dataHeight = bounds.maxY - bounds.minY
  const scaleX = (canvasWidth - margin * 2) / dataWidth
  const scaleY = (canvasHeight - margin * 2) / dataHeight
  const baseScale = Math.min(scaleX, scaleY)

  return { minX: bounds.minX, minY: bounds.minY, baseScale, margin }
}

/** OpenDRIVEまたは軌跡範囲からバウンディングボックスを計算する統合関数 */
export function calculateDataBoundingBox(
  canvasWidth: number,
  canvasHeight: number,
  roadNetworkData: RoadNetworkData | null,
  egoTrajectory: VehiclePosition[] | null,
  targetTrajectories: VehiclePosition[][],
  rotationRad: number,
  margin: number = 50
): BoundingBoxConfig | null {
  const bounds = roadNetworkData
    ? calculateRoadBounds(roadNetworkData)
    : calculateTrajectoryBounds(egoTrajectory, targetTrajectories, rotationRad)

  return calculateBoundingBox(canvasWidth, canvasHeight, bounds, margin)
}
