import { open } from '@tauri-apps/plugin-dialog';
import { invoke } from '@tauri-apps/api/core';
import './MenuBar.css';

// localStorageキー
const LS_KEY_OPENDRIVE = 'lastOpenDriveDir';
const LS_KEY_TRAJECTORY = 'lastTrajectoryDir';
const LS_KEY_SCT_RESULT = 'lastSCTResultDir';

/** ファイルパスから親ディレクトリを取得 */
function getParentDir(filePath: string): string {
  const sep = filePath.includes('\\') ? '\\' : '/';
  const lastIndex = filePath.lastIndexOf(sep);
  return lastIndex > 0 ? filePath.substring(0, lastIndex) : filePath;
}

interface MenuBarProps {
  onOpenDriveLoaded: (message: string) => void;
  onVehicleLoaded: (message: string) => void;
  onCalculateSCT: () => void;
  onLoadSCTResult: (jsonData: string) => void;
  onReset: () => void;
}

function MenuBar({ onOpenDriveLoaded, onVehicleLoaded, onCalculateSCT, onLoadSCTResult, onReset }: MenuBarProps) {
  const handleOpenDRIVE = async () => {
    try {
      const defaultPath = localStorage.getItem(LS_KEY_OPENDRIVE) || undefined;
      const selected = await open({
        multiple: false,
        defaultPath,
        filters: [{
          name: 'OpenDRIVE',
          extensions: ['xodr']
        }]
      });

      if (selected) {
        const filePath = typeof selected === 'string' ? selected : (selected as any).path;
        localStorage.setItem(LS_KEY_OPENDRIVE, getParentDir(filePath));
        const result = await invoke<string>('load_opendrive', { filePath });
        onOpenDriveLoaded(result);
      }
    } catch (error) {
      console.error('OpenDRIVE読み込みエラー:', error);
      alert(`エラー: ${error}`);
    }
  };

  const handleVehicle = async () => {
    try {
      const defaultPath = localStorage.getItem(LS_KEY_TRAJECTORY) || undefined;
      // 複数ファイル選択可能
      const selected = await open({
        multiple: true,
        defaultPath,
        filters: [{
          name: 'CSV Files',
          extensions: ['csv']
        }]
      });

      if (selected) {
        // 複数ファイルが選択された場合
        if (Array.isArray(selected)) {
          for (const file of selected) {
            const filePath = typeof file === 'string' ? file : (file as any).path;
            localStorage.setItem(LS_KEY_TRAJECTORY, getParentDir(filePath));
            const result = await invoke<string>('load_trajectory', { filePath, vehicleType: '車両' });
            onVehicleLoaded(result);
          }
        } else {
          // 単一ファイルの場合
          const filePath = typeof selected === 'string' ? selected : (selected as any).path;
          localStorage.setItem(LS_KEY_TRAJECTORY, getParentDir(filePath));
          const result = await invoke<string>('load_trajectory', { filePath, vehicleType: '車両' });
          onVehicleLoaded(result);
        }
      }
    } catch (error) {
      console.error('軌跡データ読み込みエラー:', error);
      alert(`エラー: ${error}`);
    }
  };

  const handleCalculateSCT = () => {
    onCalculateSCT();
  };

  const handleLoadSCTResult = async () => {
    try {
      const defaultPath = localStorage.getItem(LS_KEY_SCT_RESULT) || undefined;
      const selected = await open({
        directory: true,
        multiple: false,
        defaultPath,
      });

      if (selected) {
        const folderPath = typeof selected === 'string' ? selected : (selected as any).path;
        localStorage.setItem(LS_KEY_SCT_RESULT, folderPath);
        const result = await invoke<string>('load_sct_result_folder', { folderPath });
        onLoadSCTResult(result);
      }
    } catch (error) {
      console.error('SCT結果読み込みエラー:', error);
      alert(`エラー: ${error}`);
    }
  };

  return (
    <div className="menu-bar">
      <button onClick={handleOpenDRIVE}>OpenDRIVE読み込み</button>
      <button onClick={handleVehicle}>車両軌跡読み込み</button>

      <div className="menu-separator"></div>

      <button onClick={handleCalculateSCT}>SCT算出</button>
      <button onClick={handleLoadSCTResult}>結果読み込み</button>

      <div className="menu-separator"></div>

      <button onClick={onReset} style={{ backgroundColor: '#d32f2f', color: 'white' }}>
        リセット
      </button>
    </div>
  );
}

export default MenuBar;
