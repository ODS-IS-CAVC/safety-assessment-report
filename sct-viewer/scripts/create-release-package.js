import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const projectRoot = path.resolve(__dirname, '..');
const releaseDir = path.join(projectRoot, 'target', 'release');
const packageDir = path.join(projectRoot, 'release-package');

// OS別の設定
const platformConfig = {
  win32: {
    exeName: 'sct-viewer.exe',
    libs: ['esminiLib.dll', 'esminiRMLib.dll'],
    zipName: 'sct-viewer_portable_win.zip',
    extraFiles: ['vehicle_bbox.json'],
  },
  darwin: {
    exeName: 'sct-viewer',
    libs: ['libesminiLib.dylib', 'libesminiRMLib.dylib'],
    zipName: 'sct-viewer_portable_mac.zip',
    extraFiles: ['vehicle_bbox.json'],
  },
  linux: {
    exeName: 'sct-viewer',
    libs: ['libesminiLib.so', 'libesminiRMLib.so'],
    zipName: 'sct-viewer_portable_linux.zip',
    extraFiles: ['vehicle_bbox.json'],
  },
};

const config = platformConfig[process.platform];
if (!config) {
  console.warn(`⚠️  未対応のプラットフォーム: ${process.platform}`);
  process.exit(0);
}

const requiredFiles = [config.exeName, ...config.libs, ...config.extraFiles];
const zipPath = path.join(releaseDir, config.zipName);

console.log(`📦 Creating release package for ${process.platform}...`);

// ファイルの存在確認
const missingFiles = requiredFiles.filter(file => {
  const filePath = path.join(releaseDir, file);
  return !fs.existsSync(filePath);
});

if (missingFiles.length > 0) {
  console.warn('⚠️  以下のファイルが見つかりません:');
  missingFiles.forEach(file => console.warn(`   - ${file}`));
  console.warn('ビルドが完了していない可能性があります。');
  process.exit(0);
}

// 一時ディレクトリを作成
if (fs.existsSync(packageDir)) {
  fs.rmSync(packageDir, { recursive: true, force: true });
}
fs.mkdirSync(packageDir, { recursive: true });

// ファイルをコピー
console.log('📁 Copying files...');
requiredFiles.forEach(file => {
  const src = path.join(releaseDir, file);
  const dst = path.join(packageDir, file);
  fs.copyFileSync(src, dst);
  console.log(`   ✅ ${file}`);
});

// ZIPを作成
console.log('🗜️  Creating ZIP archive...');

try {
  if (fs.existsSync(zipPath)) {
    fs.unlinkSync(zipPath);
  }

  if (process.platform === 'win32') {
    // Windows: PowerShellでZIP作成
    const powershellCmd = `Compress-Archive -Path "${packageDir}\\*" -DestinationPath "${zipPath}" -Force`;
    execSync(`powershell -Command "${powershellCmd}"`, { stdio: 'inherit' });
  } else {
    // macOS/Linux: zipコマンドでZIP作成
    execSync(`cd "${packageDir}" && zip -r "${zipPath}" .`, { stdio: 'inherit' });
  }

  console.log(`✅ ZIP created: ${zipPath}`);
  console.log(`📦 Package size: ${(fs.statSync(zipPath).size / 1024 / 1024).toFixed(2)} MB`);
} catch (error) {
  console.error('❌ ZIP creation failed:', error.message);
  console.log('💡 手動でZIPを作成してください:');
  console.log(`   フォルダ: ${packageDir}`);
}

// 一時ディレクトリを削除
fs.rmSync(packageDir, { recursive: true, force: true });

console.log('✨ Release package creation completed!');
console.log(`📂 Location: ${releaseDir}`);
