import { FC, useState, useEffect } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { listen } from '@tauri-apps/api/event'
import './SCTCalculationDialog.css'

interface SCTCalculationDialogProps {
  allVehicles: { vehicleId: string }[][] // 全車両リスト
  currentEgoVehicleId: string | null // 現在の自車両ID
  onClose: () => void
  onExecute: (egoVehicleId: string, scenarioRootFolder: string, dxCalculationMode?: string) => Promise<void>
}

interface ProgressPayload {
  current: number
  total: number
  percent: number
  message: string
}

const SCTCalculationDialog: FC<SCTCalculationDialogProps> = ({ allVehicles, currentEgoVehicleId, onClose, onExecute }) => {
  const [selectedEgoVehicleId, setSelectedEgoVehicleId] = useState<string>(currentEgoVehicleId || '')
  const [scenarioRootFolder, setScenarioRootFolder] = useState<string>('')
  // dx/dy算出方法は常に'trajectory'（自車両軌跡上で最近点を探す）に固定
  const dxCalculationMode = 'trajectory'
  const [isCalculating, setIsCalculating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [currentTask, setCurrentTask] = useState('')
  const [currentCount, setCurrentCount] = useState(0)
  const [totalCount, setTotalCount] = useState(0)

  // ローカルストレージのキー
  const STORAGE_KEY = 'sct-last-scenario-root-folder'

  // 初回マウント時: 保存されたフォルダパスをロード
  useEffect(() => {
    const savedFolder = localStorage.getItem(STORAGE_KEY)
    if (savedFolder) {
      setScenarioRootFolder(savedFolder)
    }
  }, [])

  // 進捗イベントのリスナーを設定
  useEffect(() => {
    let unlisten: (() => void) | undefined

    const setupListener = async () => {
      unlisten = await listen<ProgressPayload>('sct-progress', (event) => {
        const payload = event.payload
        setProgress(payload.percent)
        setCurrentTask(payload.message)
        setCurrentCount(payload.current)
        setTotalCount(payload.total)
      })
    }

    setupListener()

    return () => {
      if (unlisten) {
        unlisten()
      }
    }
  }, [])

  const handleSelectFolder = async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: 'シナリオルートフォルダを選択（タイムスタンプフォルダが自動作成されます）',
        defaultPath: scenarioRootFolder || undefined, // 前回のフォルダをデフォルトパスとして使用
      })

      if (selected) {
        const folderPath = typeof selected === 'string' ? selected : (selected as any).path
        setScenarioRootFolder(folderPath)
        // 選択したフォルダパスをローカルストレージに保存
        localStorage.setItem(STORAGE_KEY, folderPath)
      }
    } catch (error) {
      console.error('フォルダ選択エラー:', error)
      alert(`エラー: ${error}`)
    }
  }

  const handleExecute = async () => {
    if (!selectedEgoVehicleId) {
      alert('自車両を選択してください')
      return
    }

    if (!scenarioRootFolder) {
      alert('シナリオルートフォルダを選択してください')
      return
    }

    setIsCalculating(true)
    setProgress(0)
    setCurrentTask('計算を開始しています...')

    try {
      await onExecute(selectedEgoVehicleId, scenarioRootFolder, dxCalculationMode)
      // 計算完了後、ダイアログを閉じる
      onClose()
    } catch (error) {
      console.error('SCT計算エラー:', error)
      alert(`エラー: ${error}`)
    } finally {
      setIsCalculating(false)
      setProgress(0)
      setCurrentTask('')
    }
  }

  const handleCancel = () => {
    if (isCalculating) {
      if (!confirm('計算を中断しますか？')) {
        return
      }
    }
    onClose()
  }

  return (
    <div className="sct-dialog-overlay" onClick={handleCancel}>
      <div className="sct-dialog" onClick={(e) => e.stopPropagation()}>
        <h2>SCT計算</h2>

        <div className="sct-dialog-content">
          <div className="sct-dialog-info">
            <p>選択した自車両と全対象車両についてSCTを計算します。</p>
          </div>

          <div className="sct-dialog-ego-selection" style={{ display: 'flex', alignItems: 'center' }}>
            <label style={{ fontWeight: 'bold', fontSize: '14px', width: '80px', flexShrink: 0 }}>自車両:</label>
            <select
              value={selectedEgoVehicleId}
              onChange={(e) => setSelectedEgoVehicleId(e.target.value)}
              disabled={isCalculating}
              className="ego-vehicle-select"
              style={{
                padding: '6px 8px',
                fontSize: '14px',
                width: '280px'
              }}
            >
              <option value="">自車両を選択してください</option>
              {allVehicles.map((vehicle) => {
                const vehicleId = vehicle[0]?.vehicleId || ''
                return (
                  <option key={vehicleId} value={vehicleId}>
                    {vehicleId}
                  </option>
                )
              })}
            </select>
          </div>

          <div className="sct-dialog-folder-selection" style={{ marginTop: '16px' }}>
            <label>出力先:</label>
            <div className="folder-input-group">
              <input
                type="text"
                value={scenarioRootFolder}
                readOnly
                placeholder="フォルダを選択してください（タイムスタンプフォルダが自動作成されます）"
                className="folder-path-input"
              />
              <button
                onClick={handleSelectFolder}
                disabled={isCalculating}
                className="folder-select-button"
              >
                選択
              </button>
            </div>
          </div>

          {/* dx/dy算出方法は常に「自車両軌跡上で最近点を探す」（trajectory）を使用 */}
          {/* UI選択は非表示 */}

          {isCalculating && (
            <div className="sct-dialog-progress">
              <div className="progress-info">
                <span>{currentCount} / {totalCount} ペア完了</span>
                <span>{progress}%</span>
              </div>
              <div className="progress-bar-container">
                <div className="progress-bar" style={{ width: `${progress}%` }}></div>
              </div>
              <div className="progress-text">{currentTask}</div>
            </div>
          )}
        </div>

        <div className="sct-dialog-buttons">
          <button
            onClick={handleExecute}
            disabled={isCalculating || !selectedEgoVehicleId || !scenarioRootFolder}
            className="execute-button"
          >
            {isCalculating ? '計算中...' : '実行'}
          </button>
          <button
            onClick={handleCancel}
            disabled={isCalculating}
            className="cancel-button"
          >
            キャンセル
          </button>
        </div>
      </div>
    </div>
  )
}

export default SCTCalculationDialog
