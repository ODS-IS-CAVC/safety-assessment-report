import { VehiclePosition } from '../types'

/**
 * 現在時刻に最も近い位置を二分探索で取得する。
 * タイムスタンプが昇順ソート済みであることを前提とする。
 *
 * @param trajectory - ソート済み軌跡データ
 * @param currentTime - 現在時刻（秒）
 * @returns 最も近い VehiclePosition、または trajectory が空の場合は null
 */
export const findPositionAtTime = (
  trajectory: VehiclePosition[],
  currentTime: number
): VehiclePosition | null => {
  if (trajectory.length === 0) return null
  if (trajectory.length === 1) return trajectory[0]

  let lo = 0
  let hi = trajectory.length - 1

  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if (trajectory[mid].timestamp < currentTime) {
      lo = mid + 1
    } else {
      hi = mid
    }
  }

  // lo は currentTime 以上の最小インデックス
  // lo - 1 と lo の2候補のうち currentTime に近い方を返す
  if (lo === 0) return trajectory[0]

  const before = trajectory[lo - 1]
  const after = trajectory[lo]
  return Math.abs(before.timestamp - currentTime) <= Math.abs(after.timestamp - currentTime)
    ? before
    : after
}

/**
 * 現在時刻に最も近いフレームインデックスを二分探索で取得する。
 * タイムスタンプが昇順ソート済みであることを前提とする。
 *
 * @param trajectory - ソート済み軌跡データ
 * @param currentTime - 現在時刻（秒）
 * @returns 最も近いフレームのインデックス（trajectory が空の場合は 0）
 */
export const findFrameIndexAtTime = (
  trajectory: VehiclePosition[],
  currentTime: number
): number => {
  if (trajectory.length === 0) return 0
  if (trajectory.length === 1) return 0

  let lo = 0
  let hi = trajectory.length - 1

  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if (trajectory[mid].timestamp < currentTime) {
      lo = mid + 1
    } else {
      hi = mid
    }
  }

  // lo は currentTime 以上の最小インデックス
  if (lo === 0) return 0

  const diffBefore = Math.abs(trajectory[lo - 1].timestamp - currentTime)
  const diffAfter = Math.abs(trajectory[lo].timestamp - currentTime)
  return diffBefore <= diffAfter ? lo - 1 : lo
}

/**
 * 現在時刻に最も近いフレームインデックスを取得する（タイムスタンプ比較ベース）。
 * handleStepBackward10/Forward10等で使用。
 *
 * @param trajectory - ソート済み軌跡データ
 * @param time - 現在時刻（秒）
 * @returns 最も近いフレームのインデックス
 */
export const findCurrentFrameIndex = (
  trajectory: VehiclePosition[],
  time: number
): number => {
  for (let i = 0; i < trajectory.length; i++) {
    if (Math.abs(trajectory[i].timestamp - time) < 0.001) {
      return i
    }
    if (trajectory[i].timestamp > time) {
      return Math.max(0, i - 1)
    }
  }
  return trajectory.length - 1
}

/**
 * 指定フレーム数だけステップした時刻を返す。
 * 正の値で前進、負の値で後退。
 *
 * @param trajectory - ソート済み軌跡データ
 * @param time - 現在時刻（秒）
 * @param count - ステップ数（正で前進、負で後退）
 * @returns ステップ後の時刻
 */
export const stepFrames = (
  trajectory: VehiclePosition[],
  time: number,
  count: number
): number => {
  const currentIndex = findCurrentFrameIndex(trajectory, time)
  const targetIndex = Math.max(0, Math.min(trajectory.length - 1, currentIndex + count))
  return trajectory[targetIndex].timestamp
}

/**
 * 軌跡線を Canvas に描画する。
 * 現在時刻より前の区間（過去の軌跡）は color で、
 * 現在時刻以降の区間（未来の軌跡）は colorFuture で描画する。
 *
 * @param ctx - Canvas の描画コンテキスト
 * @param trajectory - ソート済み軌跡データ
 * @param currentTime - 現在時刻（秒）
 * @param color - 過去の軌跡の色
 * @param colorFuture - 未来の軌跡の色
 * @param rotateAndTransform - ワールド座標を Canvas 座標に変換する関数
 * @param lineWidth - 軌跡線の幅（ピクセル単位、省略時は 1.0）
 */
export const drawTrajectoryLine = (
  ctx: CanvasRenderingContext2D,
  trajectory: VehiclePosition[],
  currentTime: number,
  color: string,
  colorFuture: string,
  rotateAndTransform: (x: number, y: number) => [number, number],
  lineWidth: number = 1.0
): void => {
  if (trajectory.length < 2) return

  const currentIndex = findFrameIndexAtTime(trajectory, currentTime)

  ctx.lineWidth = lineWidth

  // 現在位置まで（過去の軌跡）を描画
  if (currentIndex > 0) {
    ctx.strokeStyle = color
    ctx.beginPath()
    const [x0, y0] = rotateAndTransform(trajectory[0].x, trajectory[0].y)
    ctx.moveTo(x0, y0)
    for (let i = 1; i <= currentIndex; i++) {
      const [xi, yi] = rotateAndTransform(trajectory[i].x, trajectory[i].y)
      ctx.lineTo(xi, yi)
    }
    ctx.stroke()
  }

  // 現在位置以降（未来の軌跡）を描画
  if (currentIndex < trajectory.length - 1) {
    ctx.strokeStyle = colorFuture
    ctx.beginPath()
    const [xCurrent, yCurrent] = rotateAndTransform(
      trajectory[currentIndex].x,
      trajectory[currentIndex].y
    )
    ctx.moveTo(xCurrent, yCurrent)
    for (let i = currentIndex + 1; i < trajectory.length; i++) {
      const [xi, yi] = rotateAndTransform(trajectory[i].x, trajectory[i].y)
      ctx.lineTo(xi, yi)
    }
    ctx.stroke()
  }
}
