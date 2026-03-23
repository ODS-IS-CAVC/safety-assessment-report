import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import MenuBar from './components/MenuBar'
import RenderingArea from './components/RenderingArea'
import VideoController from './components/VideoController'
import SCTGraphArea from './components/SCTGraphArea'
import VehicleSelector from './components/VehicleSelector'
import SCTCalculationDialog from './components/SCTCalculationDialog'
import { RoadNetworkData } from './types/roadNetwork'
import { VehiclePosition, VehicleBBoxConfig, SCTDataset } from './types'
import { invoke } from '@tauri-apps/api/core'
import { stepFrames } from './utils/trajectoryRenderer'

function App() {
  const [, setOpenDriveStatus] = useState('未読み込み')
  const [roadNetworkData, setRoadNetworkData] = useState<RoadNetworkData | null>(null)
  const [originalRoadNetworkData, setOriginalRoadNetworkData] = useState<RoadNetworkData | null>(null) // フィルタリング前のオリジナルデータ

  // 全車両管理（新方式）
  const [allVehicles, setAllVehicles] = useState<VehiclePosition[][]>([])
  const [egoVehicleId, setEgoVehicleId] = useState<string | null>(null) // 自車両として指定するvehicle_id
  const [egoVehicleLocked, setEgoVehicleLocked] = useState(false) // SCT計算後に自車両を固定

  // 互換性のための計算プロパティ（useMemoで最適化して配列参照の変更を防ぐ）
  const egoTrajectory = useMemo(() =>
    egoVehicleId
      ? allVehicles.find(v => v[0]?.vehicleId === egoVehicleId) || null
      : null
  , [egoVehicleId, allVehicles])

  const targetTrajectories = useMemo(() =>
    allVehicles.filter(v => v[0]?.vehicleId !== egoVehicleId)
  , [allVehicles, egoVehicleId])

  // ステータス表示用
  const [, setVehiclesStatus] = useState('未読み込み')
  const [currentTime, setCurrentTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [minTime, setMinTime] = useState(0)
  const [maxTime, setMaxTime] = useState(0)
  const playbackSpeed = useRef(1.0) // 再生速度（実時間の倍率）
  const [vehicleBBoxConfig, setVehicleBBoxConfig] = useState<VehicleBBoxConfig | null>(null)
  const [sctDatasets, setSctDatasets] = useState<SCTDataset[]>([])
  const [selectedDatasetIndex, setSelectedDatasetIndex] = useState(0)
  // SCT計算パラメータ
  const [decelerationG, setDecelerationG] = useState(0.3) // 減速度 (G)
  const [reactionTime, setReactionTime] = useState(0.75) // 反応時間 (秒)
  // SCT算出ダイアログの表示状態
  const [showSCTDialog, setShowSCTDialog] = useState(false)

  // 車両バウンディングボックス情報を読み込み
  useEffect(() => {
    const loadVehicleBBox = async () => {
      try {
        const jsonData = await invoke<string>('load_vehicle_bbox')
        const config: VehicleBBoxConfig = JSON.parse(jsonData)
        setVehicleBBoxConfig(config)
      } catch (error) {
        console.error('車両バウンディングボックス読み込みエラー:', error)
      }
    }
    loadVehicleBBox()
  }, [])

  // OpenDRIVEデータをそのまま使用（フィルタリング削除）
  // 可視範囲外の車線は renderRoadNetwork 内でカリングされるため不要
  useEffect(() => {
    if (!originalRoadNetworkData) return
    setRoadNetworkData(originalRoadNetworkData)
  }, [originalRoadNetworkData])

  const handleOpenDriveLoaded = (jsonData: string) => {
    try {
      const data: RoadNetworkData = JSON.parse(jsonData)
      setOriginalRoadNetworkData(data) // オリジナルを保存
      setRoadNetworkData(data) // 初期状態はフィルタリングなし

      const roadCount = data.roads.length
      const laneCount = data.roads.reduce((sum, road) => sum + road.lanes.length, 0)
      setOpenDriveStatus(`${roadCount} roads, ${laneCount} lanes`)
    } catch (error) {
      console.error('JSON parse error:', error)
      setOpenDriveStatus(`エラー: ${error}`)
    }
  }

  const handleVehicleLoaded = (jsonData: string) => {
    try {
      // Rustから送られるデータは既にcamelCaseに変換されている（VehiclePositionDTO）
      const positions: VehiclePosition[] = JSON.parse(jsonData)

      if (positions.length === 0) {
        alert('エラー: データが空です')
        return
      }

      const vehicleId = positions[0].vehicleId

      // 既に読み込まれている車両と重複していないかチェック
      const isDuplicate = allVehicles.some(trajectory =>
        trajectory.length > 0 && trajectory[0].vehicleId === vehicleId
      )

      if (isDuplicate) {
        alert(`車両 ${vehicleId} は既に読み込まれています。`)
        return
      }

      setAllVehicles(prev => [...prev, positions])

      // 最初の車両を自車両として設定
      if (allVehicles.length === 0) {
        setEgoVehicleId(vehicleId)
      }

      // 時刻範囲を更新
      if (positions.length > 0) {
        const min = positions[0].timestamp
        const max = positions[positions.length - 1].timestamp

        if (allVehicles.length === 0) {
          setMinTime(min)
          setMaxTime(max)
          setCurrentTime(min)
        } else {
          setMinTime(prevMin => Math.min(prevMin, min))
          setMaxTime(prevMax => Math.max(prevMax, max))
        }
      }

      setVehiclesStatus(`${allVehicles.length + 1}台`)
    } catch (error) {
      console.error('JSON parse error:', error)
      alert(`エラー: ${error}`)
    }
  }

  // 再生制御
  const handlePlayPause = () => {
    setIsPlaying(!isPlaying)
  }

  const handleTimeChange = (time: number) => {
    setCurrentTime(time)
    setIsPlaying(false)
  }

  // 先頭に戻る
  const handleRewind = () => {
    setCurrentTime(minTime)
    setIsPlaying(false)
  }

  // 1コマ戻る
  const handleStepBackward = useCallback(() => {
    if (!egoTrajectory || egoTrajectory.length === 0) return

    setCurrentTime(prevTime => {
      // 現在時刻より前のフレームを探す
      for (let i = egoTrajectory.length - 1; i >= 0; i--) {
        if (egoTrajectory[i].timestamp < prevTime - 0.001) {
          setIsPlaying(false)
          return egoTrajectory[i].timestamp
        }
      }
      return prevTime
    })
  }, [egoTrajectory])

  // 1コマ進む
  const handleStepForward = useCallback(() => {
    if (!egoTrajectory || egoTrajectory.length === 0) return

    setCurrentTime(prevTime => {
      // 現在時刻より後のフレームを探す
      for (let i = 0; i < egoTrajectory.length; i++) {
        if (egoTrajectory[i].timestamp > prevTime + 0.001) {
          setIsPlaying(false)
          return egoTrajectory[i].timestamp
        }
      }
      return prevTime
    })
  }, [egoTrajectory])

  // 10コマ戻る（長押し用）
  const handleStepBackward10 = useCallback(() => {
    if (!egoTrajectory || egoTrajectory.length === 0) return
    setCurrentTime(prevTime => stepFrames(egoTrajectory, prevTime, -10))
    setIsPlaying(false)
  }, [egoTrajectory])

  // 10コマ進む（長押し用）
  const handleStepForward10 = useCallback(() => {
    if (!egoTrajectory || egoTrajectory.length === 0) return
    setCurrentTime(prevTime => stepFrames(egoTrajectory, prevTime, 10))
    setIsPlaying(false)
  }, [egoTrajectory])

  // SCT結果読み込み（フォルダからすべてのファイルを読み込み）
  const handleLoadSCTResult = (jsonData: string) => {
    try {
      const datasets: SCTDataset[] = JSON.parse(jsonData)

      if (datasets.length === 0) {
        alert('SCT結果ファイルが見つかりませんでした')
        return
      }

      // すべてのデータセットを置き換え
      setSctDatasets(datasets)
      setSelectedDatasetIndex(0) // 最初のデータセットを選択

      // 自車両を設定してロック（SCT計算時と同様）
      const egoId = datasets[0].egoVehicleId
      setEgoVehicleId(egoId)
      setEgoVehicleLocked(true)

    } catch (error) {
      console.error('JSON parse error:', error)
      alert(`エラー: SCT結果の読み込みに失敗しました`)
    }
  }

  // SCT計算ダイアログを開く
  const handleCalculateSCT = () => {
    // データチェック
    if (!egoTrajectory) {
      alert('自車両軌跡を読み込んでください')
      return
    }
    if (targetTrajectories.length === 0) {
      alert('対象車両軌跡を読み込んでください')
      return
    }
    if (!vehicleBBoxConfig) {
      alert('車両バウンディングボックス情報の読み込みに失敗しています')
      return
    }

    // ダイアログを表示
    setShowSCTDialog(true)
  }

  // SCT総当り計算を実行
  const executeSCTCalculation = async (selectedEgoVehicleId: string, scenarioRootFolder: string, dxCalculationMode?: string) => {
    if (!vehicleBBoxConfig || allVehicles.length === 0) {
      throw new Error('必要なデータが読み込まれていません')
    }

    // 選択された自車両軌跡を取得
    const selectedEgoTrajectory = allVehicles.find(v => v[0]?.vehicleId === selectedEgoVehicleId)
    if (!selectedEgoTrajectory) {
      throw new Error('選択された自車両が見つかりません')
    }

    // 全車両の軌跡を集める
    const allTrajectories = allVehicles

    // GをNEWTON単位（m/s²）に変換: 1G ≈ 9.80665 m/s²
    const amaxValue = decelerationG * 9.80665

    const result = await invoke<string>('calculate_sct_with_timestamp_folder', {
      egoVehicleId: selectedEgoVehicleId,
      allTrajectories: allTrajectories,
      vehicleBboxData: vehicleBBoxConfig.vehicles,
      scenarioRootFolder: scenarioRootFolder,
      amax: amaxValue,
      tau: reactionTime,
      dxCalculationMode: dxCalculationMode,
    })

    // resultにはタイムスタンプフォルダのパスが含まれる想定
    const timestampFolderMatch = result.match(/出力先: (.+)/)
    const timestampFolder = timestampFolderMatch ? timestampFolderMatch[1] : null

    // 自車両を設定してロック
    setEgoVehicleId(selectedEgoVehicleId)
    setEgoVehicleLocked(true)

    // 計算完了後、自動的に結果を読み込む
    if (timestampFolder) {
      try {
        const loadResult = await invoke<string>('load_sct_result_folder', { folderPath: timestampFolder })
        handleLoadSCTResult(loadResult)
        alert(`✓ SCT計算が完了しました！\n\n${result}\n\n結果を自動的に読み込みました。`)
      } catch (loadError) {
        console.error('SCT結果の自動読み込みエラー:', loadError)
        alert(`✓ SCT計算が完了しました！\n\n${result}\n\n※結果の自動読み込みに失敗しました。`)
      }
    } else {
      alert(`✓ SCT計算が完了しました！\n\n${result}`)
    }
  }

  // リセット処理
  const handleReset = () => {
    // 確認ダイアログを表示
    if (!confirm('すべてのデータをリセットしますか？\n（車両バウンディングボックス情報は保持されます）')) {
      return
    }

    // すべてのstateを初期値に戻す
    setOpenDriveStatus('未読み込み')
    setRoadNetworkData(null)
    setOriginalRoadNetworkData(null)
    setAllVehicles([])
    setEgoVehicleId(null)
    setEgoVehicleLocked(false)
    setVehiclesStatus('未読み込み')
    setCurrentTime(0)
    setIsPlaying(false)
    setMinTime(0)
    setMaxTime(0)
    setSctDatasets([])
    setSelectedDatasetIndex(0)
  }

  // 再生ループ（30FPSに制限して描画負荷を軽減）
  useEffect(() => {
    if (!isPlaying || !egoTrajectory) return

    let animationFrameId: number
    let lastUpdateTime = performance.now()
    const targetFPS = 30 // 描画を30FPSに制限
    const frameInterval = 1000 / targetFPS // 約33.33ms

    const animate = (timestamp: number) => {
      const elapsed = timestamp - lastUpdateTime

      // 30FPS制限：前回更新から十分時間が経過した場合のみ更新
      if (elapsed >= frameInterval) {
        const deltaTime = elapsed / 1000 // 秒に変換
        lastUpdateTime = timestamp

        setCurrentTime(prevTime => {
          const nextTime = prevTime + deltaTime * playbackSpeed.current
          if (nextTime >= maxTime) {
            setIsPlaying(false)
            return maxTime
          }
          return nextTime
        })
      }

      if (isPlaying) {
        animationFrameId = requestAnimationFrame(animate)
      }
    }

    animationFrameId = requestAnimationFrame(animate)

    return () => {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId)
      }
    }
  }, [isPlaying, maxTime, egoTrajectory])



  return (
    <div className="app">
      <MenuBar
        onOpenDriveLoaded={handleOpenDriveLoaded}
        onVehicleLoaded={handleVehicleLoaded}
        onCalculateSCT={handleCalculateSCT}
        onLoadSCTResult={handleLoadSCTResult}
        onReset={handleReset}
      />

      {showSCTDialog && (
        <SCTCalculationDialog
          allVehicles={allVehicles}
          currentEgoVehicleId={egoVehicleId}
          onClose={() => setShowSCTDialog(false)}
          onExecute={executeSCTCalculation}
        />
      )}

      <div className="main-content">
        <div className="left-panel">
          {/* SCTパラメータ設定（1行で横並び） */}
          <div className="parameters-section" style={{
            padding: '8px',
            border: '1px solid #ddd',
            borderRadius: '4px',
            marginBottom: '10px',
            backgroundColor: '#f9f9f9',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            flexWrap: 'wrap'
          }}>
            <span style={{ fontWeight: 'bold', fontSize: '13px' }}>SCT計算:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <label htmlFor="deceleration-input" style={{ fontSize: '12px' }}>減速度:</label>
              <input
                id="deceleration-input"
                type="number"
                value={decelerationG}
                onChange={(e) => setDecelerationG(parseFloat(e.target.value) || 0)}
                step="0.1"
                min="0"
                max="1"
                style={{
                  width: '60px',
                  padding: '2px 4px',
                  border: '1px solid #ccc',
                  borderRadius: '3px',
                  fontSize: '12px'
                }}
              />
              <span style={{ fontSize: '12px', color: '#666' }}>G</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <label htmlFor="reaction-time-input" style={{ fontSize: '12px' }}>反応時間:</label>
              <input
                id="reaction-time-input"
                type="number"
                value={reactionTime}
                onChange={(e) => setReactionTime(parseFloat(e.target.value) || 0)}
                step="0.05"
                min="0"
                max="5"
                style={{
                  width: '60px',
                  padding: '2px 4px',
                  border: '1px solid #ccc',
                  borderRadius: '3px',
                  fontSize: '12px'
                }}
              />
              <span style={{ fontSize: '12px', color: '#666' }}>秒</span>
            </div>
          </div>

          {/* 車両選択 */}
          {allVehicles.length > 0 && (
            <VehicleSelector
              allVehicles={allVehicles}
              egoVehicleId={egoVehicleId}
              egoVehicleLocked={egoVehicleLocked}
              onEgoVehicleChange={setEgoVehicleId}
              sctDatasets={sctDatasets}
              selectedIndex={selectedDatasetIndex}
              onSelectVehicle={setSelectedDatasetIndex}
            />
          )}

          {/* SCTグラフエリア */}
          {sctDatasets.length > 0 && (
            <div className="graph-section">
              <SCTGraphArea
                sctDataset={sctDatasets[selectedDatasetIndex]}
                currentTime={currentTime}
              />
            </div>
          )}
        </div>

        <div className="right-panel">
          <RenderingArea
            roadNetworkData={roadNetworkData}
            egoTrajectory={egoTrajectory}
            targetTrajectories={targetTrajectories}
            currentTime={currentTime}
            isPlaying={isPlaying}
            vehicleBBoxConfig={vehicleBBoxConfig}
            sctDatasets={sctDatasets}
            selectedDatasetIndex={selectedDatasetIndex}
          />
          {egoTrajectory && (
            <VideoController
              minTime={minTime}
              maxTime={maxTime}
              currentTime={currentTime}
              isPlaying={isPlaying}
              onTimeChange={handleTimeChange}
              onPlayPause={handlePlayPause}
              onRewind={handleRewind}
              onStepBackward={handleStepBackward}
              onStepForward={handleStepForward}
              onStepBackward10={handleStepBackward10}
              onStepForward10={handleStepForward10}
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default App
