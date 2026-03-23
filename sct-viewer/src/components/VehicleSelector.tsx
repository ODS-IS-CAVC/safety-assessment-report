import { SCTDataset, VehiclePosition } from '../types'
import './VehicleSelector.css'

interface VehicleSelectorProps {
  allVehicles: VehiclePosition[][]
  egoVehicleId: string | null
  egoVehicleLocked: boolean
  onEgoVehicleChange: (vehicleId: string) => void
  sctDatasets: SCTDataset[]
  selectedIndex: number
  onSelectVehicle: (index: number) => void
}

function VehicleSelector({
  allVehicles,
  egoVehicleId,
  egoVehicleLocked,
  onEgoVehicleChange,
  sctDatasets,
  selectedIndex,
  onSelectVehicle
}: VehicleSelectorProps) {
  if (allVehicles.length === 0) {
    return null
  }

  const handleEgoChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newEgoVehicleId = event.target.value
    onEgoVehicleChange(newEgoVehicleId)

    // 自車両変更時に、新しい自車両に対応する最初の対象車両を選択
    const newFilteredDatasets = sctDatasets
      .map((dataset, index) => ({ dataset, index }))
      .filter(({ dataset }) => dataset.egoVehicleId === newEgoVehicleId)

    if (newFilteredDatasets.length > 0) {
      onSelectVehicle(newFilteredDatasets[0].index)
    }
  }

  const handleTargetChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    // フィルタリングされたリストのインデックスから元のインデックスに変換
    const filteredIndex = parseInt(event.target.value, 10)
    const originalIndex = filteredDatasets[filteredIndex]?.index
    if (originalIndex !== undefined) {
      onSelectVehicle(originalIndex)
    }
  }

  // 現在の自車両に対する対象車両リストをフィルタ
  const filteredDatasets = sctDatasets
    .map((dataset, index) => ({ dataset, index }))
    .filter(({ dataset }) => dataset.egoVehicleId === egoVehicleId)

  // 現在のselectedIndexがフィルタリング後のリストのどこにあるか
  const selectedFilteredIndex = filteredDatasets.findIndex(({ index }) => index === selectedIndex)

  return (
    <div className="vehicle-selector">
      {/* 自車両選択 */}
      <div style={{ marginBottom: '3px', display: 'flex', alignItems: 'center' }}>
        <label htmlFor="ego-vehicle-select" style={{ fontWeight: 'bold', fontSize: '14px', width: '80px', flexShrink: 0 }}>
          自車両:
        </label>
        <select
          id="ego-vehicle-select"
          value={egoVehicleId || ''}
          onChange={handleEgoChange}
          disabled={egoVehicleLocked}
          className="vehicle-select"
          style={{
            padding: '6px 8px',
            fontSize: '14px',
            width: '280px',
            backgroundColor: egoVehicleLocked ? '#f5f5f5' : '#fff',
            cursor: egoVehicleLocked ? 'not-allowed' : 'pointer'
          }}
        >
          {allVehicles.map((vehicle, idx) => {
            const vehicleId = vehicle[0]?.vehicleId || ''
            return (
              <option key={vehicleId || `empty-${idx}`} value={vehicleId}>
                {vehicleId || '(不明)'}
              </option>
            )
          })}
        </select>
      </div>

      {/* 対象車両選択（常に表示） */}
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <label htmlFor="target-vehicle-select" style={{ fontWeight: 'bold', fontSize: '14px', width: '80px', flexShrink: 0 }}>対象車両:</label>
        <select
          id="target-vehicle-select"
          value={selectedFilteredIndex >= 0 ? selectedFilteredIndex : 0}
          onChange={handleTargetChange}
          className="vehicle-select"
          style={{
            padding: '6px 8px',
            fontSize: '14px',
            width: '280px'
          }}
          disabled={filteredDatasets.length === 0}
        >
          {filteredDatasets.length === 0 ? (
            <option value="">SCT計算を実行してください</option>
          ) : (
            filteredDatasets.map(({ dataset, index }, filteredIndex) => (
              <option key={index} value={filteredIndex}>
                {dataset.targetVehicleId}
              </option>
            ))
          )}
        </select>
      </div>
    </div>
  )
}

export default VehicleSelector
