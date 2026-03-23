import { FC } from 'react'
import { VehiclePosition, SCTDataset, SCTRow } from '../types'

type TablePosition = 'top-right' | 'bottom-right' | 'bottom-left' | 'top-left' | 'hidden'

interface VelocityInfoTableProps {
  egoTrajectory: VehiclePosition[] | null
  targetTrajectories: VehiclePosition[][]
  currentTime: number
  sctDatasets: SCTDataset[]
  tablePosition: TablePosition
}

interface TableData {
  vehicleId: string
  color: string
  speed: string
  dx: string
  dy: string
  vx: string
  vy: string
  sctx: string
  scty: string
  shouldHighlight: boolean // SCT値が8以下で強調表示
}

const VelocityInfoTable: FC<VelocityInfoTableProps> = ({
  egoTrajectory,
  targetTrajectories,
  currentTime,
  sctDatasets,
  tablePosition,
}) => {
  const getTablePositionStyle = (): React.CSSProperties => {
    const baseStyle: React.CSSProperties = {
      position: 'absolute',
      backgroundColor: 'rgba(0, 0, 0, 0.85)',
      color: 'white',
      borderCollapse: 'collapse',
      fontSize: '11px',
      fontFamily: 'Monaco, "Courier New", monospace',
      zIndex: 150, // VideoController (z-index: 100) より上に表示
      border: '1px solid #555',
      borderRadius: '4px',
      backdropFilter: 'blur(4px)',
    }

    switch (tablePosition) {
      case 'top-right':
        return { ...baseStyle, top: '60px', right: '10px' }
      case 'bottom-right':
        // VideoControllerと重ならないように余裕を持たせる (VideoController height ~60-70px + margin)
        return { ...baseStyle, bottom: '90px', right: '10px' }
      case 'bottom-left':
        // VideoControllerと重ならないように余裕を持たせる
        return { ...baseStyle, bottom: '90px', left: '10px' }
      case 'top-left':
        return { ...baseStyle, top: '60px', left: '10px' }
      default:
        return { ...baseStyle, top: '60px', right: '10px' }
    }
  }

  // 自車両データを取得
  const getEgoData = (): TableData | null => {
    if (!egoTrajectory) return null
    const egoPos = egoTrajectory.find(pos => Math.abs(pos.timestamp - currentTime) < 0.05)
    if (!egoPos) return null

    return {
      vehicleId: egoPos.vehicleId,
      color: '#FF4444',
      speed: (egoPos.velocity * 3.6).toFixed(1).padStart(5, ' '),
      dx: '-',
      dy: '-',
      vx: '-',
      vy: '-',
      sctx: '-',
      scty: '-',
      shouldHighlight: false,
    }
  }

  // 対象車両データを取得（現在の自車両に対応するもののみ）
  const getTargetData = (): TableData[] => {
    const colors = ['#4444FF', '#44FF44', '#FF44FF', '#00CED1', '#FFD700']
    const data: TableData[] = []

    if (!egoTrajectory || sctDatasets.length === 0) {
      return data
    }

    const egoVehicleId = egoTrajectory[0]?.vehicleId
    if (!egoVehicleId) {
      return data
    }

    // 現在の自車両に対応するSCTデータセットのみをフィルタ
    const egoSctDatasets = sctDatasets.filter(ds => ds.egoVehicleId === egoVehicleId)

    egoSctDatasets.forEach((sctDataset, index) => {
      // このSCTデータセットの対象車両の軌跡を探す
      const targetTrajectory = targetTrajectories.find(traj =>
        traj.length > 0 && traj[0].vehicleId === sctDataset.targetVehicleId
      )

      if (!targetTrajectory) return

      const targetPos = targetTrajectory.find(pos => Math.abs(pos.timestamp - currentTime) < 0.05)
      if (!targetPos) return

      const color = colors[index % colors.length]
      let dxText = '-'
      let dyText = '-'
      let vxText = '-'
      let vyText = '-'
      let sctxText = '-'
      let sctyText = '-'
      let shouldHighlight = false

      const frameIndex = egoTrajectory.findIndex(p => Math.abs(p.timestamp - currentTime) < 0.05)
      const sctRow = sctDataset.data.find((row: SCTRow) => row.frame === frameIndex)
      if (sctRow) {
        // 相対距離（m）- 移動平均値を使用
        if (sctRow.dx_ma !== null && sctRow.dx_ma !== undefined) {
          dxText = sctRow.dx_ma.toFixed(1).padStart(5, ' ')
        }
        if (sctRow.dy_ma !== null && sctRow.dy_ma !== undefined) {
          dyText = sctRow.dy_ma.toFixed(1).padStart(5, ' ')
        }

        // 相対速度（km/h）- 移動平均値を使用
        if (sctRow.vx_ma !== null && sctRow.vx_ma !== undefined) {
          vxText = (sctRow.vx_ma * 3.6).toFixed(1).padStart(5, ' ')
        }
        if (sctRow.vy_ma !== null && sctRow.vy_ma !== undefined) {
          vyText = (sctRow.vy_ma * 3.6).toFixed(1).padStart(5, ' ')
        }

        // SCT（秒）
        if (sctRow.sctx !== null && sctRow.sctx !== undefined) {
          sctxText = sctRow.sctx.toFixed(2).padStart(5, ' ')
          // SCTxが8以下なら強調
          if (sctRow.sctx <= 8) {
            shouldHighlight = true
          }
        }
        if (sctRow.scty !== null && sctRow.scty !== undefined) {
          sctyText = sctRow.scty.toFixed(2).padStart(5, ' ')
          // SCTyが8以下なら強調
          if (sctRow.scty <= 8) {
            shouldHighlight = true
          }
        }
      }

      data.push({
        vehicleId: targetPos.vehicleId,
        color,
        speed: (targetPos.velocity * 3.6).toFixed(1).padStart(5, ' '),
        dx: dxText,
        dy: dyText,
        vx: vxText,
        vy: vyText,
        sctx: sctxText,
        scty: sctyText,
        shouldHighlight,
      })
    })

    return data
  }

  const egoData = getEgoData()
  const targetData = getTargetData()

  // hiddenの場合は表示しない
  if (tablePosition === 'hidden') {
    return null
  }

  return (
    <table style={getTablePositionStyle()}>
      <thead>
        <tr>
          <th style={{ padding: '2px 8px', textAlign: 'left', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>車両ID</th>
          <th style={{ padding: '2px 8px', textAlign: 'right', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>
            速度<span style={{ fontSize: '9px', opacity: 0.7 }}>(km/h)</span>
          </th>
          <th style={{ padding: '2px 8px', textAlign: 'right', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>
            dx<span style={{ fontSize: '9px', opacity: 0.7 }}>(m)</span>
          </th>
          <th style={{ padding: '2px 8px', textAlign: 'right', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>
            vx<span style={{ fontSize: '9px', opacity: 0.7 }}>(km/h)</span>
          </th>
          <th style={{ padding: '2px 8px', textAlign: 'right', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>
            SCT x<span style={{ fontSize: '9px', opacity: 0.7 }}>(s)</span>
          </th>
          <th style={{ padding: '2px 8px', textAlign: 'right', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>
            dy<span style={{ fontSize: '9px', opacity: 0.7 }}>(m)</span>
          </th>
          <th style={{ padding: '2px 8px', textAlign: 'right', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>
            vy<span style={{ fontSize: '9px', opacity: 0.7 }}>(km/h)</span>
          </th>
          <th style={{ padding: '2px 8px', textAlign: 'right', borderBottom: '1px solid #555', whiteSpace: 'nowrap' }}>
            SCT y<span style={{ fontSize: '9px', opacity: 0.7 }}>(s)</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {/* 自車両 */}
        {egoData && (
          <tr key="ego">
            <td style={{ color: egoData.color, padding: '2px 8px' }}>{egoData.vehicleId}</td>
            <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{egoData.speed}</td>
            <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{egoData.dx}</td>
            <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{egoData.vx}</td>
            <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{egoData.sctx}</td>
            <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{egoData.dy}</td>
            <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{egoData.vy}</td>
            <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{egoData.scty}</td>
          </tr>
        )}

        {/* 対象車両 */}
        {targetData.map((data, index) => {
          // SCTx または SCTy が8以下の場合、背景色を変更
          const rowBackgroundColor = data.shouldHighlight ? 'rgba(255, 165, 0, 0.15)' : 'transparent'

          return (
            <tr key={`target-${index}`} style={{ backgroundColor: rowBackgroundColor }}>
              <td style={{ color: data.color, padding: '2px 8px' }}>{data.vehicleId}</td>
              <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{data.speed}</td>
              <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{data.dx}</td>
              <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{data.vx}</td>
              <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{data.sctx}</td>
              <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{data.dy}</td>
              <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{data.vy}</td>
              <td style={{ color: 'white', padding: '2px 8px', textAlign: 'right', width: '60px' }}>{data.scty}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default VelocityInfoTable
export type { TablePosition }
