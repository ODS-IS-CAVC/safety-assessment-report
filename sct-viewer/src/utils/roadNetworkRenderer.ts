import { RoadNetworkData } from '../types/roadNetwork'
import { ColorMode } from '../components/RenderingControls'

// 車線ごとのバウンディングボックスキャッシュ
interface LaneBBox {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

// 全体バウンディングボックスのキャッシュ
interface GlobalBBox {
  minX: number
  maxX: number
  minY: number
  maxY: number
  dataWidth: number
  dataHeight: number
  baseScale: number
}

// 車線ごとのPath2Dキャッシュ
interface LanePathCache {
  path: Path2D
  roadIndex: number
  laneIndex: number
  bbox: LaneBBox
}

// 道路データごとの空間インデックス（初回計算後にキャッシュ）
// const spatialIndexCache = new WeakMap<RoadNetworkData, Map<string, LaneBBox>>()
const globalBBoxCache = new WeakMap<RoadNetworkData, GlobalBBox>()
const lanePathCache = new WeakMap<RoadNetworkData, LanePathCache[]>()

/**
 * キャッシュを強制的に再構築
 */
export function rebuildRoadNetworkCache(roadData: RoadNetworkData | null) {
  if (!roadData) return
  // 既存のキャッシュを削除
  globalBBoxCache.delete(roadData)
  lanePathCache.delete(roadData)
}

// フィルタリング機能は削除（可視範囲カリングで十分高速なため不要）

/**
 * 可視範囲内かどうかをチェック
 */
function isLaneVisible(
  laneBBox: LaneBBox,
  canvasWidth: number,
  canvasHeight: number,
  transformX: (x: number) => number,
  transformY: (y: number) => number
): boolean {
  // 車線のバウンディングボックスをCanvas座標に変換
  const canvasMinX = transformX(laneBBox.minX)
  const canvasMaxX = transformX(laneBBox.maxX)
  const canvasMinY = transformY(laneBBox.maxY) // Y軸反転に注意
  const canvasMaxY = transformY(laneBBox.minY)

  // マージンを追加（画面外でも少し余裕を持って描画）
  const margin = 100

  // 可視範囲外判定
  if (canvasMaxX < -margin) return false
  if (canvasMinX > canvasWidth + margin) return false
  if (canvasMaxY < -margin) return false
  if (canvasMinY > canvasHeight + margin) return false

  return true
}

/**
 * 道路ネットワークの描画
 */
export function renderRoadNetwork(
  ctx: CanvasRenderingContext2D,
  canvasWidth: number,
  canvasHeight: number,
  data: RoadNetworkData | null,
  zoom: number,
  offsetX: number,
  offsetY: number,
  _colorMode: ColorMode,
  laneWidth: number,
  _showRoadIds: boolean,
  rotation: number = 0,
  externalBoundingBox: { minX: number, minY: number, baseScale: number, margin: number } | null = null
) {
  // 背景をクリア
  ctx.fillStyle = '#2a2a2a'
  ctx.fillRect(0, 0, canvasWidth, canvasHeight)

  // データがない場合は描画しない
  if (!data) {
    return
  }

  // バウンディングボックスの取得
  let minX: number, minY: number, baseScale: number, margin: number

  if (externalBoundingBox) {
    // 外部から渡されたboundingBoxを使用（回転を考慮済み）
    ({ minX, minY, baseScale, margin } = externalBoundingBox)
  } else {
    // 内部でboundingBoxを計算（回転なしの従来動作）
    let globalBBox = globalBBoxCache.get(data)
    if (!globalBBox) {
      let bbMinX = Infinity, bbMaxX = -Infinity
      let bbMinY = Infinity, bbMaxY = -Infinity

      data.roads.forEach(road => {
        road.lanes.forEach(lane => {
          lane.points.forEach(point => {
            bbMinX = Math.min(bbMinX, point.x)
            bbMaxX = Math.max(bbMaxX, point.x)
            bbMinY = Math.min(bbMinY, point.y)
            bbMaxY = Math.max(bbMaxY, point.y)
          })
        })
      })

      // データが空の場合
      if (!isFinite(bbMinX) || !isFinite(bbMaxX) || !isFinite(bbMinY) || !isFinite(bbMaxY)) {
        ctx.fillStyle = '#ffffff'
        ctx.font = '16px Arial'
        ctx.textAlign = 'center'
        ctx.fillText('道路データがありません', canvasWidth / 2, canvasHeight / 2)
        return
      }

      const dataWidth = bbMaxX - bbMinX
      const dataHeight = bbMaxY - bbMinY

      // 基本スケールを計算（アスペクト比を維持）
      margin = 50
      const scaleX = (canvasWidth - margin * 2) / dataWidth
      const scaleY = (canvasHeight - margin * 2) / dataHeight
      baseScale = Math.min(scaleX, scaleY)

      globalBBox = {
        minX: bbMinX,
        maxX: bbMaxX,
        minY: bbMinY,
        maxY: bbMaxY,
        dataWidth,
        dataHeight,
        baseScale
      }
      globalBBoxCache.set(data, globalBBox)
    }

    minX = globalBBox.minX
    minY = globalBBox.minY
    baseScale = globalBBox.baseScale
    margin = 50
  }

  // Canvas中心
  const canvasCenterX = canvasWidth / 2
  const canvasCenterY = canvasHeight / 2

  // 回転角度をラジアンに変換
  const rotationRad = (rotation * Math.PI) / 180

  // Canvas transformを使用して座標変換を最適化
  // 全ての座標変換を一度のtransform設定で実行
  ctx.save()

  // 1. 画面中央を原点に移動
  ctx.translate(canvasCenterX, canvasCenterY)

  // 2. オフセットを適用
  ctx.translate(offsetX, offsetY)

  // 3. ズームを適用
  ctx.scale(zoom, zoom)

  // 4. 回転を適用
  ctx.rotate(rotationRad)

  // 5. ベース座標系の原点を設定（道路データの左下を原点に）
  ctx.translate(margin - canvasCenterX, canvasCenterY - margin)

  // 6. Y軸反転とベーススケールを適用
  ctx.scale(baseScale, -baseScale)

  // 7. 道路データの原点（minX, minY）を0,0に
  ctx.translate(-minX, -minY)

  // 簡易座標変換関数（可視判定用、Canvas transformは使わない）
  // 回転を考慮した変換を行うため、x,yの両方を受け取る関数に変更
  const rotateAndTransformToCanvas = (x: number, y: number): [number, number] => {
    // 1. 回転を適用
    const rotatedX = x * Math.cos(rotationRad) - y * Math.sin(rotationRad)
    const rotatedY = x * Math.sin(rotationRad) + y * Math.cos(rotationRad)

    // 2. ベース座標に変換
    const baseX = ((rotatedX - minX) * baseScale) + margin
    const baseY = canvasHeight - (((rotatedY - minY) * baseScale) + margin)

    // 3. 相対座標化
    const relativeX = baseX - canvasCenterX
    const relativeY = baseY - canvasCenterY

    // 4. ズーム適用
    const zoomedX = relativeX * zoom
    const zoomedY = relativeY * zoom

    // 5. オフセット適用
    const offsettedX = zoomedX + offsetX
    const offsettedY = zoomedY + offsetY

    // 6. Canvas座標に変換
    return [offsettedX + canvasCenterX, offsettedY + canvasCenterY]
  }

  // 後方互換性のため、個別のtransform関数も保持
  // 回転がない場合は正確、回転がある場合は近似値（可視判定用）
  const transformX = (x: number) => {
    // 回転がない場合は従来の計算
    if (rotation === 0) {
      const baseX = ((x - minX) * baseScale) + margin
      const relativeX = baseX - canvasCenterX
      const zoomedX = relativeX * zoom
      const offsettedX = zoomedX + offsetX
      return offsettedX + canvasCenterX
    }
    // 回転がある場合は、y=0として近似
    return rotateAndTransformToCanvas(x, 0)[0]
  }

  const transformY = (y: number) => {
    // 回転がない場合は従来の計算
    if (rotation === 0) {
      const baseY = canvasHeight - (((y - minY) * baseScale) + margin)
      const relativeY = baseY - canvasCenterY
      const zoomedY = relativeY * zoom
      const offsettedY = zoomedY + offsetY
      return offsettedY + canvasCenterY
    }
    // 回転がある場合は、x=0として近似
    return rotateAndTransformToCanvas(0, y)[1]
  }

  // Path2Dキャッシュの取得または作成（初回のみ）
  let lanePaths = lanePathCache.get(data)
  if (!lanePaths) {
    lanePaths = []

    data.roads.forEach((road, roadIndex) => {
      road.lanes.forEach((lane, laneIndex) => {
        if (lane.points.length < 2) return

        // 車線のバウンディングボックスを計算
        let laneMinX = Infinity, laneMaxX = -Infinity
        let laneMinY = Infinity, laneMaxY = -Infinity

        lane.points.forEach(point => {
          laneMinX = Math.min(laneMinX, point.x)
          laneMaxX = Math.max(laneMaxX, point.x)
          laneMinY = Math.min(laneMinY, point.y)
          laneMaxY = Math.max(laneMaxY, point.y)
        })

        // Path2Dオブジェクトを作成（中心線）
        const path = new Path2D()
        const firstPoint = lane.points[0]
        path.moveTo(firstPoint.x, firstPoint.y)

        for (let i = 1; i < lane.points.length; i++) {
          const point = lane.points[i]
          path.lineTo(point.x, point.y)
        }

        lanePaths!.push({
          path,
          roadIndex,
          laneIndex,
          bbox: {
            minX: laneMinX,
            maxX: laneMaxX,
            minY: laneMinY,
            maxY: laneMaxY
          }
        })
      })
    })

    lanePathCache.set(data, lanePaths)
  }

  // 各車線を描画（Path2Dキャッシュを使用、可視範囲内のみ）
  let renderedLanes = 0
  let skippedLanes = 0

  lanePaths.forEach(lanePathData => {
    const { path, bbox } = lanePathData

    // 可視判定
    if (!isLaneVisible(bbox, canvasWidth, canvasHeight, transformX, transformY)) {
      skippedLanes++
      return // 可視範囲外ならスキップ
    }

    renderedLanes++

    // 車線の色を白に設定
    ctx.strokeStyle = '#ffffff'

    // Canvas transformでスケールされるので、lineWidthは元のサイズを逆算
    ctx.lineWidth = Math.min(laneWidth * zoom, 10) / (zoom * baseScale)

    // Path2Dで一括描画（超高速）
    ctx.stroke(path)

    // 道路ID表示は省略（パフォーマンス優先）
    // 必要な場合はshowRoadIds && zoom > 10.0など条件を厳しくする
  })

  // Canvas transformをリセット
  ctx.restore()

  // スケール情報を表示（画面下側・固定サイズ）
  ctx.fillStyle = '#ffffff'
  ctx.font = '12px Arial'
  ctx.textAlign = 'left'
  const totalLanes = data.roads.reduce((sum, road) => sum + road.lanes.length, 0)
  // externalBoundingBoxを使う場合は範囲情報を表示しない
  if (!externalBoundingBox && globalBBoxCache.has(data)) {
    const cachedBBox = globalBBoxCache.get(data)!
    ctx.fillText(`範囲: ${cachedBBox.dataWidth.toFixed(1)}m × ${cachedBBox.dataHeight.toFixed(1)}m`, 10, canvasHeight - 70)
  }
  ctx.fillText(`Roads: ${data.roads.length}`, 10, canvasHeight - 55)
  ctx.fillText(`Lanes: ${totalLanes}`, 10, canvasHeight - 40)
  ctx.fillText(`描画: ${renderedLanes} / スキップ: ${skippedLanes}`, 10, canvasHeight - 25)
}
