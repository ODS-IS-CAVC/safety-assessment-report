import { FC } from 'react'

type ColorMode = 'default' | 'lane' | 'road'
type TablePosition = 'top-right' | 'bottom-right' | 'bottom-left' | 'top-left' | 'hidden'
type SCBDisplayMode = 'vehicle-based' | 'position-based'

// TODO: 将来的にconfig.jsonから読み込む
const ROTATION_ANGLE_STEP = 90 // 回転ボタンの角度ステップ（度）

// UI表示制御フラグ
const SHOW_COLOR_MODE_BUTTON = false // 色分けモードボタンの表示
const SHOW_ROAD_ID_BUTTON = false    // 道路IDボタンの表示
const SHOW_SCB_MODE_BUTTON = false   // SCB表示モードボタンの表示
const SHOW_SWAP_SCB_BUTTON = false   // 車両入替ボタンの表示

interface RenderingControlsProps {
  zoom: number
  minZoom: number
  onZoomChange: (zoom: number) => void
  colorMode: ColorMode
  onColorModeChange: (mode: ColorMode) => void
  showRoadIds: boolean
  onShowRoadIdsChange: (show: boolean) => void
  showVehicleNames: boolean
  onShowVehicleNamesChange: (show: boolean) => void
  showReferencePoints: boolean
  onShowReferencePointsChange: (show: boolean) => void
  followMode: boolean
  onFollowModeChange: (follow: boolean) => void
  tablePosition: TablePosition
  onTablePositionChange: () => void
  trajectoryRotation: number
  onTrajectoryRotationChange: (rotation: number) => void
  scbDisplayMode: SCBDisplayMode
  onSCBDisplayModeChange: (mode: SCBDisplayMode) => void
  swapSCBAxes: boolean
  onSwapSCBAxesChange: (swap: boolean) => void
  onResetView: () => void
  onFitToVehicles: () => void
}

const RenderingControls: FC<RenderingControlsProps> = ({
  zoom,
  minZoom,
  onZoomChange,
  colorMode,
  onColorModeChange,
  showRoadIds,
  onShowRoadIdsChange,
  showVehicleNames,
  onShowVehicleNamesChange,
  showReferencePoints,
  onShowReferencePointsChange,
  followMode,
  onFollowModeChange,
  tablePosition,
  onTablePositionChange,
  trajectoryRotation,
  onTrajectoryRotationChange,
  scbDisplayMode,
  onSCBDisplayModeChange,
  swapSCBAxes,
  onSwapSCBAxesChange,
  onResetView,
  onFitToVehicles,
}) => {
  const handleZoomChange = (newZoom: number) => {
    onZoomChange(newZoom)
  }

  const cycleColorMode = () => {
    if (colorMode === 'default') onColorModeChange('lane')
    else if (colorMode === 'lane') onColorModeChange('road')
    else onColorModeChange('default')
  }

  const cycleSCBDisplayMode = () => {
    onSCBDisplayModeChange(scbDisplayMode === 'vehicle-based' ? 'position-based' : 'vehicle-based')
  }

  // 回転角度を0-359度の範囲に正規化
  const normalizeRotation = (angle: number): number => {
    const normalized = angle % 360
    return normalized < 0 ? normalized + 360 : normalized
  }

  const handleRotationChange = (delta: number) => {
    const newRotation = normalizeRotation(trajectoryRotation + delta)
    onTrajectoryRotationChange(newRotation)
  }

  return (
    <div className="top-controls">
      <div className="zoom-slider-control">
        <label>ズーム:</label>
        <input
          type="range"
          min={minZoom}
          max="200"
          step="0.1"
          value={zoom}
          onChange={(e) => handleZoomChange(parseFloat(e.target.value))}
          style={{ width: '150px' }}
        />
      </div>
      {SHOW_COLOR_MODE_BUTTON && (
        <button
          className="color-mode-button"
          onClick={cycleColorMode}
          title="車線の色分けモードを変更"
        >
          色: {colorMode === 'default' ? 'デフォルト' : colorMode === 'lane' ? '車線別' : '道路別'}
        </button>
      )}
      {SHOW_ROAD_ID_BUTTON && (
        <button
          className={`follow-button ${showRoadIds ? 'active' : ''}`}
          onClick={() => onShowRoadIdsChange(!showRoadIds)}
          title="道路ID表示のON/OFF"
        >
          ID
        </button>
      )}
      <button
        className={`follow-button ${showVehicleNames ? 'active' : ''}`}
        onClick={() => onShowVehicleNamesChange(!showVehicleNames)}
        title="車両名表示のON/OFF"
      >
        名前
      </button>
      <button
        className={`follow-button ${showReferencePoints ? 'active' : ''}`}
        onClick={() => onShowReferencePointsChange(!showReferencePoints)}
        title="計算参照点表示のON/OFF (S1, T1, P1, T2, P2, DX, DY)"
      >
        参照点
      </button>
      <button
        className={`follow-button ${followMode ? 'active' : ''}`}
        onClick={() => onFollowModeChange(!followMode)}
        title="自車両追従モードのON/OFF"
      >
        追従
      </button>
      {SHOW_SCB_MODE_BUTTON && (
        <button
          className="color-mode-button"
          onClick={cycleSCBDisplayMode}
          title="SCB表示方式を変更"
        >
          SCB: {scbDisplayMode === 'vehicle-based' ? '自車基準' : '位置基準'}
        </button>
      )}
      {SHOW_SWAP_SCB_BUTTON && (
        <button
          className={`follow-button ${swapSCBAxes ? 'active' : ''}`}
          onClick={() => onSwapSCBAxesChange(!swapSCBAxes)}
          title="SCBの表示車両を入れ替え（自車⇔対象車両）"
        >
          車両入替
        </button>
      )}
      <button
        className="table-position-button"
        onClick={onTablePositionChange}
        title="速度情報テーブルの表示位置を切り替え（右上→右下→左下→左上→非表示）"
      >
        {tablePosition === 'hidden' ? (
          <span style={{ fontSize: '14px', fontWeight: 'bold' }}>✕</span>
        ) : (
          <div className="position-grid">
            <div className={`position-indicator ${tablePosition === 'top-left' ? 'active' : ''}`}></div>
            <div className={`position-indicator ${tablePosition === 'top-right' ? 'active' : ''}`}></div>
            <div className={`position-indicator ${tablePosition === 'bottom-left' ? 'active' : ''}`}></div>
            <div className={`position-indicator ${tablePosition === 'bottom-right' ? 'active' : ''}`}></div>
          </div>
        )}
      </button>
      <div className="trajectory-rotation-control">
        <button
          className="rotation-button"
          onClick={() => handleRotationChange(-ROTATION_ANGLE_STEP)}
          title={`軌跡を時計回りに${ROTATION_ANGLE_STEP}度回転`}
        >
          ↻
        </button>
        <span className="rotation-label">{trajectoryRotation}°</span>
        <button
          className="rotation-button"
          onClick={() => handleRotationChange(ROTATION_ANGLE_STEP)}
          title={`軌跡を反時計回りに${ROTATION_ANGLE_STEP}度回転`}
        >
          ↺
        </button>
        <button
          className="rotation-reset-button"
          onClick={() => onTrajectoryRotationChange(0)}
          title="回転をリセット"
        >
          0°
        </button>
      </div>
      <button className="reset-button" onClick={onResetView} title="道路にフィット（リセット）">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
      </button>
      <button className="fit-button" onClick={onFitToVehicles} title="車両軌跡全体にフィット">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
          <path d="M8 8l-4 4 4 4M16 8l4 4-4 4" />
        </svg>
      </button>
    </div>
  )
}

export default RenderingControls
export type { ColorMode, TablePosition, SCBDisplayMode }
