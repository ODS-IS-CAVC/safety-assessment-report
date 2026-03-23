import { memo } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { SCTDataset } from '../types'
import './SCTGraphArea.css'

// Chart.jsの初期化
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

interface SCTGraphAreaProps {
  sctDataset: SCTDataset | null
  currentTime: number
}

function SCTGraphAreaComponent({ sctDataset, currentTime }: SCTGraphAreaProps) {

  if (!sctDataset) {
    return (
      <div className="sct-graph-area">
        <div className="no-data-message">
          <p>SCT結果を読み込んでください</p>
          <p className="hint">メニューバーの「結果 &gt; 結果読み込み」からCSVファイルを選択してください</p>
        </div>
      </div>
    )
  }

  // 表示範囲を前後1.5秒（合計3秒）に制限
  const timeRange = 1.5 // 前後1.5秒
  const minTime = currentTime - timeRange
  const maxTime = currentTime + timeRange

  // 表示範囲内のデータのみをフィルタ
  const visibleData = sctDataset.data.filter(row =>
    row.timestamp >= minTime && row.timestamp <= maxTime
  )

  // 現在時刻に最も近いデータポイントのインデックスを見つける（visibleData内）
  let closestIndex = 0
  let minDiff = Infinity
  visibleData.forEach((row, index) => {
    const diff = Math.abs(row.timestamp - currentTime)
    if (diff < minDiff) {
      minDiff = diff
      closestIndex = index
    }
  })

  // 縦方向SCTグラフのデータ
  const dataX = {
    labels: visibleData.map((row) => row.timestamp),
    datasets: [
      {
        label: 'SCTX',
        data: visibleData.map((row) => row.sctx),
        borderColor: 'rgb(54, 162, 235)', // 青色に変更（Pythonスクリプト準拠）
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        pointRadius: visibleData.map((_, index) => index === closestIndex ? 5 : 0), // 現在時刻に最も近い点をマーク
        borderWidth: 2,
      },
    ],
  }

  // 横方向SCTグラフのデータ
  const dataY = {
    labels: visibleData.map((row) => row.timestamp),
    datasets: [
      {
        label: 'SCTY',
        data: visibleData.map((row) => row.scty),
        borderColor: 'rgb(54, 162, 235)', // 青色に変更（Pythonスクリプト準拠）
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        pointRadius: visibleData.map((_, index) => index === closestIndex ? 5 : 0), // 現在時刻に最も近い点をマーク
        borderWidth: 2,
      },
    ],
  }

  const options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false, // アニメーションを無効化してパフォーマンス向上
    scales: {
      x: {
        type: 'linear',
        min: minTime,
        max: maxTime,
        title: {
          display: true,
          text: 'Time (s)',
        },
      },
      y: {
        min: 0,
        max: 8,
        title: {
          display: true,
          text: 'SCT [s]',
        },
      },
    },
    plugins: {
      legend: {
        display: false, // Chart.jsの凡例を非表示
      },
      title: {
        display: false,
      },
    },
  }

  return (
    <div className="sct-graph-area">
      <div className="graph-header">
        <h3>SCT グラフ表示</h3>
      </div>

      <div className="graphs-container">
        <div className="graph-section">
          <div className="graph-section-header">
            <h4>縦方向</h4>
            <div className="custom-legend">
              <div className="legend-item">
                <span className="legend-box" style={{ backgroundColor: 'rgb(54, 162, 235)' }}></span>
                <span className="legend-label">SCTX</span>
              </div>
            </div>
          </div>
          <div className="graph-canvas">
            <Line data={dataX} options={options} />
          </div>
        </div>

        <div className="graph-section">
          <div className="graph-section-header">
            <h4>横方向</h4>
            <div className="custom-legend">
              <div className="legend-item">
                <span className="legend-box" style={{ backgroundColor: 'rgb(54, 162, 235)' }}></span>
                <span className="legend-label">SCTY</span>
              </div>
            </div>
          </div>
          <div className="graph-canvas">
            <Line data={dataY} options={options} />
          </div>
        </div>
      </div>
    </div>
  )
}

// React.memoで最適化: sctDatasetが変わらない限り再レンダリングしない
const SCTGraphArea = memo(SCTGraphAreaComponent)

export default SCTGraphArea
