import { useRef, useCallback, useEffect } from 'react'
import './VideoController.css'
import rewindIcon from '../assets/icons/rewind.svg'
import stepBackwardIcon from '../assets/icons/step-backward.svg'
import playIcon from '../assets/icons/play.svg'
import pauseIcon from '../assets/icons/pause.svg'
import stepForwardIcon from '../assets/icons/step-forward.svg'

interface VideoControllerProps {
  minTime: number
  maxTime: number
  currentTime: number
  isPlaying: boolean
  onTimeChange: (time: number) => void
  onPlayPause: () => void
  onRewind: () => void
  onStepBackward: () => void
  onStepForward: () => void
  onStepBackward10: () => void
  onStepForward10: () => void
}

function VideoController({
  minTime,
  maxTime,
  currentTime,
  isPlaying,
  onTimeChange,
  onPlayPause,
  onRewind,
  onStepBackward,
  onStepForward,
  onStepBackward10: _onStepBackward10,
  onStepForward10: _onStepForward10
}: VideoControllerProps) {
  // マウス用タイマー
  const repeatIntervalRef = useRef<number | null>(null)
  const repeatTimeoutRef = useRef<number | null>(null)

  // キーボード用タイマー（マウスとは独立）
  const keyRepeatIntervalRef = useRef<number | null>(null)
  const keyRepeatTimeoutRef = useRef<number | null>(null)
  const pressedKeysRef = useRef<Set<string>>(new Set())

  // コールバック関数のrefを保持（クロージャ問題を回避）
  const onPlayPauseRef = useRef(onPlayPause)
  const onStepBackwardRef = useRef(onStepBackward)
  const onStepForwardRef = useRef(onStepForward)

  // コールバックが変更されたら常に最新版をrefに保存
  useEffect(() => {
    onPlayPauseRef.current = onPlayPause
    onStepBackwardRef.current = onStepBackward
    onStepForwardRef.current = onStepForward
  }, [onPlayPause, onStepBackward, onStepForward])

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onTimeChange(parseFloat(e.target.value))
  }

  const formatTime = (time: number) => {
    return time.toFixed(2) + 's'
  }

  // リピート処理のクリーンアップ（マウス用）
  const cleanupRepeat = () => {
    if (repeatTimeoutRef.current !== null) {
      window.clearTimeout(repeatTimeoutRef.current)
      repeatTimeoutRef.current = null
    }
    if (repeatIntervalRef.current !== null) {
      window.clearInterval(repeatIntervalRef.current)
      repeatIntervalRef.current = null
    }
  }

  // キーボード用のクリーンアップ関数
  const cleanupKeyRepeat = () => {
    if (keyRepeatTimeoutRef.current !== null) {
      window.clearTimeout(keyRepeatTimeoutRef.current)
      keyRepeatTimeoutRef.current = null
    }
    if (keyRepeatIntervalRef.current !== null) {
      window.clearInterval(keyRepeatIntervalRef.current)
      keyRepeatIntervalRef.current = null
    }
  }

  // マウスダウン時のハンドラー（戻る）
  const handleStepBackwardMouseDown = useCallback(() => {
    // 初回実行
    onStepBackward()

    // 長押しリピート開始（300ms後）
    repeatTimeoutRef.current = window.setTimeout(() => {
      // 1フレームずつスキップする処理を50msごとに実行（滑らかな動き）
      repeatIntervalRef.current = window.setInterval(() => {
        onStepBackward()
      }, 50)
    }, 300)

    const handleUp = () => {
      cleanupRepeat()
      window.removeEventListener('mouseup', handleUp)
      window.removeEventListener('touchend', handleUp)
    }

    window.addEventListener('mouseup', handleUp, { once: false })
    window.addEventListener('touchend', handleUp, { once: false })
  }, [onStepBackward])

  // マウスダウン時のハンドラー（進む）
  const handleStepForwardMouseDown = useCallback(() => {
    // 初回実行
    onStepForward()

    // 長押しリピート開始（300ms後）
    repeatTimeoutRef.current = window.setTimeout(() => {
      // 1フレームずつスキップする処理を50msごとに実行（滑らかな動き）
      repeatIntervalRef.current = window.setInterval(() => {
        onStepForward()
      }, 50)
    }, 300)

    const handleUp = () => {
      cleanupRepeat()
      window.removeEventListener('mouseup', handleUp)
      window.removeEventListener('touchend', handleUp)
    }

    window.addEventListener('mouseup', handleUp, { once: false })
    window.addEventListener('touchend', handleUp, { once: false })
  }, [onStepForward])

  // キーボードイベントハンドラー
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // スペースキー: 再生/一時停止（リピート防止）
      if (e.key === ' ' || e.code === 'Space') {
        if (pressedKeysRef.current.has(e.key)) {
          return
        }
        e.preventDefault()
        onPlayPauseRef.current()
        pressedKeysRef.current.add(e.key)
        return
      }

      // 左矢印キー: コマ戻し（長押し対応）
      if (e.key === 'ArrowLeft') {
        e.preventDefault()

        if (pressedKeysRef.current.has(e.key)) {
          return
        }

        pressedKeysRef.current.add(e.key)

        // 初回実行
        onStepBackwardRef.current()

        // 長押しリピート開始（300ms後）
        keyRepeatTimeoutRef.current = window.setTimeout(() => {
          keyRepeatIntervalRef.current = window.setInterval(() => {
            onStepBackwardRef.current()
          }, 50)
        }, 300)
        return
      }

      // 右矢印キー: コマ送り（長押し対応）
      if (e.key === 'ArrowRight') {
        e.preventDefault()

        if (pressedKeysRef.current.has(e.key)) {
          return
        }

        pressedKeysRef.current.add(e.key)

        // 初回実行
        onStepForwardRef.current()

        // 長押しリピート開始（300ms後）
        keyRepeatTimeoutRef.current = window.setTimeout(() => {
          keyRepeatIntervalRef.current = window.setInterval(() => {
            onStepForwardRef.current()
          }, 50)
        }, 300)
        return
      }
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      pressedKeysRef.current.delete(e.key)

      // 左右矢印キーの長押しリピートをクリーンアップ
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        cleanupKeyRepeat()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
      cleanupKeyRepeat()
    }
  }, [])

  return (
    <div className="video-controller">
      <button className="control-button" onClick={onRewind} title="先頭に戻る">
        <img src={rewindIcon} alt="先頭に戻る" className="button-icon" />
      </button>

      <button
        className="control-button"
        onMouseDown={handleStepBackwardMouseDown}
        title="1コマ戻る（長押しで連続再生）&#10;キーボード: ←"
      >
        <img src={stepBackwardIcon} alt="1コマ戻る" className="button-icon" />
      </button>

      <button className="play-button" onClick={onPlayPause} title="再生/一時停止&#10;キーボード: スペース">
        <img src={isPlaying ? pauseIcon : playIcon} alt={isPlaying ? '一時停止' : '再生'} className="button-icon" />
      </button>

      <button
        className="control-button"
        onMouseDown={handleStepForwardMouseDown}
        title="1コマ進む（長押しで連続再生）&#10;キーボード: →"
      >
        <img src={stepForwardIcon} alt="1コマ進む" className="button-icon" />
      </button>

      <div className="time-display">
        {formatTime(currentTime)}
      </div>

      <input
        type="range"
        className="time-slider"
        min={minTime}
        max={maxTime}
        step={0.01}
        value={currentTime}
        onChange={handleSliderChange}
      />

      <div className="time-range">
        <span>{formatTime(minTime)}</span>
        <span>{formatTime(maxTime)}</span>
      </div>
    </div>
  )
}

export default VideoController
