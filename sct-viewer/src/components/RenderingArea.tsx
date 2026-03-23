import { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react'
import type { RoadNetworkData } from '../types/roadNetwork'
import { VehiclePosition, VehicleBBoxConfig, SCTDataset } from '../types'
import './RenderingArea.css'
import RenderingControls, { ColorMode, TablePosition, SCBDisplayMode } from './RenderingControls'
import VelocityInfoTable from './VelocityInfoTable'
import { renderRoadNetwork } from '../utils/roadNetworkRenderer'
import { renderVehicles } from '../utils/vehicleRenderer'
import { calculateRoadBounds, calculateTrajectoryBounds, calculateBoundingBox, calculateDataBoundingBox } from '../utils/coordinateUtils'

interface RenderingAreaProps {
  roadNetworkData: RoadNetworkData | null
  egoTrajectory: VehiclePosition[] | null
  targetTrajectories: VehiclePosition[][]
  currentTime: number
  isPlaying: boolean
  vehicleBBoxConfig: VehicleBBoxConfig | null
  sctDatasets: SCTDataset[]
  selectedDatasetIndex: number
}

function RenderingArea({ roadNetworkData, egoTrajectory, targetTrajectories, currentTime, isPlaying: _isPlaying, vehicleBBoxConfig, sctDatasets, selectedDatasetIndex }: RenderingAreaProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [zoom, setZoom] = useState(1.0)
  const [minZoom, setMinZoom] = useState(0.1) // 軌跡範囲に基づく最小ズーム
  const [offsetX, setOffsetX] = useState(0)
  const [offsetY, setOffsetY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [colorMode, setColorMode] = useState<ColorMode>('default')
  const [trajectoryRotation, setTrajectoryRotation] = useState(0) // 軌跡の回転角度（度数）デフォルト0度
  const [followMode, setFollowMode] = useState(true) // 自車両追従モード
  const [showRoadIds, setShowRoadIds] = useState(false) // 道路ID表示のOn/Off
  const [showVehicleNames, setShowVehicleNames] = useState(true) // 車両名表示のOn/Off
  const [showReferencePoints, setShowReferencePoints] = useState(true) // P1,P2,T1,T2,S1計算参照点表示のOn/Off
  const [tablePosition, setTablePosition] = useState<TablePosition>('top-right') // 速度情報テーブルの表示位置
  const [scbDisplayMode, setSCBDisplayMode] = useState<SCBDisplayMode>('vehicle-based') // SCB表示モード（デフォルト: 自車基準）
  const [swapSCBAxes, setSwapSCBAxes] = useState(false) // SCBの縦軸・横軸入れ替え
  const prevOffsetRef = useRef({ x: 0, y: 0 }) // 前回のoffset値を保存
  const [canvasReady, setCanvasReady] = useState(false) // Canvas初期化完了フラグ
  const prevDatasetIndexRef = useRef<number>(-1) // 前回のデータセットインデックス

  // テーブル位置を次の角に切り替える（右上 → 右下 → 左下 → 左上 → 非表示）
  const cycleTablePosition = useCallback(() => {
    const positions: TablePosition[] = ['top-right', 'bottom-right', 'bottom-left', 'top-left', 'hidden']
    const currentIndex = positions.indexOf(tablePosition)
    const nextIndex = (currentIndex + 1) % positions.length
    setTablePosition(positions[nextIndex])
  }, [tablePosition])

  // すべての車両軌跡にフィット
  const fitToVehicles = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    if (!egoTrajectory && targetTrajectories.length === 0) return

    const rotationRad = (trajectoryRotation * Math.PI) / 180
    const margin = 50

    // 1. 軌跡の範囲を計算
    const trajBounds = calculateTrajectoryBounds(egoTrajectory, targetTrajectories, rotationRad)
    if (!isFinite(trajBounds.minX)) return

    const trajCenterX = (trajBounds.minX + trajBounds.maxX) / 2
    const trajCenterY = (trajBounds.minY + trajBounds.maxY) / 2

    // 2. 軌跡のbaseScaleを計算
    const trajBBox = calculateBoundingBox(canvas.width, canvas.height, trajBounds, margin)
    if (!trajBBox) return
    const trajBaseScale = trajBBox.baseScale

    // 3. 描画時のbaseScaleを計算
    const drawBBox = roadNetworkData
      ? calculateBoundingBox(canvas.width, canvas.height, calculateRoadBounds(roadNetworkData), margin)
      : trajBBox
    if (!drawBBox) return
    const drawBaseScale = drawBBox.baseScale

    // 4. zoomを調整
    const targetZoom = trajBaseScale / drawBaseScale

    // 5. 軌跡中心を画面中心に配置
    const baseCenterX = ((trajCenterX - drawBBox.minX) * drawBaseScale) + margin
    const baseCenterY = canvas.height - (((trajCenterY - drawBBox.minY) * drawBaseScale) + margin)

    const canvasCenterX = canvas.width / 2
    const canvasCenterY = canvas.height / 2

    const relativeCenterX = baseCenterX - canvasCenterX
    const relativeCenterY = baseCenterY - canvasCenterY

    setMinZoom(0.9)
    setZoom(targetZoom)
    setOffsetX(-relativeCenterX * targetZoom)
    setOffsetY(-relativeCenterY * targetZoom)
  }, [egoTrajectory, targetTrajectories, trajectoryRotation, roadNetworkData])

  // 道路にフィット（リセット）
  const resetView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const rotationRad = (trajectoryRotation * Math.PI) / 180
    const margin = 50

    // バウンディングボックスを計算
    const bounds = roadNetworkData
      ? calculateRoadBounds(roadNetworkData)
      : calculateTrajectoryBounds(egoTrajectory, targetTrajectories, rotationRad)

    const bbox = calculateBoundingBox(canvas.width, canvas.height, bounds, margin)
    if (!bbox) return

    // データの中心座標
    const centerX = (bounds.minX + bounds.maxX) / 2
    const centerY = (bounds.minY + bounds.maxY) / 2

    // データ中心をベース座標に変換
    const baseCenterX = ((centerX - bbox.minX) * bbox.baseScale) + margin
    const baseCenterY = canvas.height - (((centerY - bbox.minY) * bbox.baseScale) + margin)

    // 画面中心からの相対座標
    const canvasCenterX = canvas.width / 2
    const canvasCenterY = canvas.height / 2
    const relativeCenterX = baseCenterX - canvasCenterX
    const relativeCenterY = baseCenterY - canvasCenterY

    setOffsetX(-relativeCenterX)
    setOffsetY(-relativeCenterY)
    setZoom(1.0)
  }, [roadNetworkData, egoTrajectory, targetTrajectories, trajectoryRotation])

  // 初期表示 & OpenDRIVE読み込み時: 道路を画面中心にフィット
  useEffect(() => {
    if (roadNetworkData) {
      resetView()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roadNetworkData])

  // 軌跡読み込み時: 車両軌跡全体にフィット
  useEffect(() => {
    if (egoTrajectory || targetTrajectories.length > 0) {
      fitToVehicles()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [egoTrajectory, targetTrajectories])

  // 自車両追従モード: 自車両を画面中心に配置
  // 追従モード時のカメラ位置計算（レンダリング前に同期的に実行）
  const calculateFollowModeOffset = useCallback((
    canvas: HTMLCanvasElement,
    boundingBox: { minX: number, minY: number, baseScale: number, margin: number } | null,
    egoTraj: VehiclePosition[],
    time: number,
    currentZoom: number,
    rotation: number
  ): { x: number, y: number } | null => {
    if (!followMode || !egoTraj || egoTraj.length === 0 || !boundingBox) return null

    // 現在時刻に最も近い自車両位置を取得
    let closestPos = egoTraj[0]
    let minDiff = Math.abs(egoTraj[0].timestamp - time)

    for (const pos of egoTraj) {
      const diff = Math.abs(pos.timestamp - time)
      if (diff < minDiff) {
        minDiff = diff
        closestPos = pos
      }
    }

    const { minX, minY, baseScale, margin } = boundingBox

    // 回転を考慮した座標変換
    const rotationRad = (rotation * Math.PI) / 180
    const rotatedX = closestPos.x * Math.cos(rotationRad) - closestPos.y * Math.sin(rotationRad)
    const rotatedY = closestPos.x * Math.sin(rotationRad) + closestPos.y * Math.cos(rotationRad)

    // 統一座標系でのベース座標を計算
    const baseX = ((rotatedX - minX) * baseScale) + margin
    const baseY = canvas.height - (((rotatedY - minY) * baseScale) + margin)

    // Canvas中心
    const canvasCenterX = canvas.width / 2
    const canvasCenterY = canvas.height / 2

    // 自車両が画面中心に来るようにオフセットを調整
    const relativeX = baseX - canvasCenterX
    const relativeY = baseY - canvasCenterY

    const newOffsetX = -relativeX * currentZoom
    const newOffsetY = -relativeY * currentZoom

    return { x: newOffsetX, y: newOffsetY }
  }, [followMode])

  // Canvas初期化とリサイズ処理（useLayoutEffectで同期的に実行）
  useLayoutEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const resizeCanvas = () => {
      const container = canvas.parentElement
      if (container) {
        const newWidth = container.clientWidth
        const newHeight = container.clientHeight
        canvas.width = newWidth
        canvas.height = newHeight
      }
    }

    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)

    // Canvas初期化完了を次のフレームで通知
    requestAnimationFrame(() => {
      setCanvasReady(true)
    })

    return () => {
      window.removeEventListener('resize', resizeCanvas)
    }
  }, []) // 空の依存配列：初回のみ実行

  // 描画処理
  useEffect(() => {
    if (!canvasReady) {
      return
    }

    const canvas = canvasRef.current
    if (!canvas) {
      return
    }

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      return
    }

    // 背景をクリア
    ctx.fillStyle = '#2a2a2a'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // 車両軌跡もない場合は何も描画せずに終了
    if (!roadNetworkData && !egoTrajectory && targetTrajectories.length === 0) {
      return
    }

    // データセットが変更された場合の参照更新
    if (prevDatasetIndexRef.current !== selectedDatasetIndex) {
      prevDatasetIndexRef.current = selectedDatasetIndex
    }

    // バウンディングボックスを計算（OpenDRIVEまたは軌跡範囲）
    const rotationRad = (trajectoryRotation * Math.PI) / 180
    const boundingBox = calculateDataBoundingBox(canvas.width, canvas.height, roadNetworkData, egoTrajectory, targetTrajectories, rotationRad)

    // 追従モード時のカメラオフセットを計算（boundingBox計算後に実行）
    let currentOffsetX = offsetX
    let currentOffsetY = offsetY

    if (followMode && egoTrajectory) {
      const newOffset = calculateFollowModeOffset(canvas, boundingBox, egoTrajectory, currentTime, zoom, trajectoryRotation)
      if (newOffset) {
        // 前回の値と比較して大きく変わった場合のみ更新（無限ループ防止）
        if (Math.abs(newOffset.x - prevOffsetRef.current.x) > 0.1 || Math.abs(newOffset.y - prevOffsetRef.current.y) > 0.1) {
          prevOffsetRef.current = newOffset
          currentOffsetX = newOffset.x
          currentOffsetY = newOffset.y
          // レンダリング後に状態を更新（次回のドラッグ操作等のため）
          setOffsetX(newOffset.x)
          setOffsetY(newOffset.y)
        }
      }
    }

    // 道路ネットワークと車両の描画（追従モード時は計算したオフセットを使用）
    // boundingBoxを渡すことで、道路と車両が同じ座標系を使用
    // OpenDRIVEは回転させない（trajectoryRotation = 0）
    renderRoadNetwork(ctx, canvas.width, canvas.height, roadNetworkData, zoom, currentOffsetX, currentOffsetY, colorMode, 0.01, showRoadIds, 0, boundingBox)
    renderVehicles(ctx, canvas.width, canvas.height, egoTrajectory, targetTrajectories, currentTime, zoom, currentOffsetX, currentOffsetY, trajectoryRotation, boundingBox, vehicleBBoxConfig, sctDatasets, selectedDatasetIndex, showVehicleNames, showReferencePoints, scbDisplayMode, swapSCBAxes)
  }, [canvasReady, roadNetworkData, egoTrajectory, targetTrajectories, currentTime, zoom, offsetX, offsetY, colorMode, trajectoryRotation, vehicleBBoxConfig, sctDatasets, selectedDatasetIndex, showRoadIds, showVehicleNames, showReferencePoints, followMode, calculateFollowModeOffset, scbDisplayMode, swapSCBAxes])

  // ズーム処理（マウスホイール）
  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()

    const canvas = canvasRef.current
    if (!canvas) return

    // ズーム係数
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1
    // 最小ズームは軌跡範囲に基づいて制限、最大200倍
    const newZoom = Math.max(minZoom, Math.min(200, zoom * zoomFactor))

    // 画面中央を基準にズーム（offsetをスケール）
    const scaleChange = newZoom / zoom
    setOffsetX(offsetX * scaleChange)
    setOffsetY(offsetY * scaleChange)
    setZoom(newZoom)
  }

  // ドラッグ開始
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDragging(true)
    setDragStart({ x: e.clientX - offsetX, y: e.clientY - offsetY })
  }

  // ドラッグ中
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDragging) return
    setOffsetX(e.clientX - dragStart.x)
    setOffsetY(e.clientY - dragStart.y)
  }

  // ドラッグ終了
  const handleMouseUp = () => {
    setIsDragging(false)
  }

  // ズーム変更ハンドラー
  const handleZoomChange = (newZoom: number) => {
    // 最小ズーム制限を適用
    const clampedZoom = Math.max(minZoom, Math.min(200, newZoom))
    const scaleChange = clampedZoom / zoom
    setOffsetX(offsetX * scaleChange)
    setOffsetY(offsetY * scaleChange)
    setZoom(clampedZoom)
  }

  return (
    <div className="rendering-area">
      <canvas
        ref={canvasRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      />
      <RenderingControls
        zoom={zoom}
        minZoom={minZoom}
        onZoomChange={handleZoomChange}
        colorMode={colorMode}
        onColorModeChange={setColorMode}
        showRoadIds={showRoadIds}
        onShowRoadIdsChange={setShowRoadIds}
        showVehicleNames={showVehicleNames}
        onShowVehicleNamesChange={setShowVehicleNames}
        showReferencePoints={showReferencePoints}
        onShowReferencePointsChange={setShowReferencePoints}
        followMode={followMode}
        onFollowModeChange={setFollowMode}
        tablePosition={tablePosition}
        onTablePositionChange={cycleTablePosition}
        trajectoryRotation={trajectoryRotation}
        onTrajectoryRotationChange={setTrajectoryRotation}
        scbDisplayMode={scbDisplayMode}
        onSCBDisplayModeChange={setSCBDisplayMode}
        swapSCBAxes={swapSCBAxes}
        onSwapSCBAxesChange={setSwapSCBAxes}
        onResetView={resetView}
        onFitToVehicles={fitToVehicles}
      />

      {/* 速度情報テーブル */}
      <VelocityInfoTable
        egoTrajectory={egoTrajectory}
        targetTrajectories={targetTrajectories}
        currentTime={currentTime}
        sctDatasets={sctDatasets}
        tablePosition={tablePosition}
      />
      <div className="bottom-right-info">
        <p>マウスホイール: ズーム | ドラッグ: 移動</p>
      </div>
    </div>
  )
}


export default RenderingArea
