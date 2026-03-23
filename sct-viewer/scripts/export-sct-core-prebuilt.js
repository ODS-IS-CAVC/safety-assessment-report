import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');
const releaseDir = path.join(projectRoot, 'target', 'release');
const prebuiltDir = path.join(projectRoot, 'sct-core', 'prebuilt');

// OS別のライブラリ名とプラットフォームディレクトリ
const platformConfig = {
  win32:  { libName: 'sct_core.dll',        dir: 'win' },
  darwin: { libName: 'libsct_core.dylib',   dir: 'mac' },
  linux:  { libName: 'libsct_core.so',      dir: 'linux' },
};

const config = platformConfig[process.platform];
if (!config) {
  console.warn(`⚠️  未対応のプラットフォーム: ${process.platform}`);
  process.exit(0);
}

const srcPath = path.join(releaseDir, config.libName);
const dstDir = path.join(prebuiltDir, config.dir);
const dstPath = path.join(dstDir, config.libName);

if (!fs.existsSync(srcPath)) {
  console.warn(`⚠️  ${config.libName} が見つかりません: ${srcPath}`);
  process.exit(0);
}

fs.mkdirSync(dstDir, { recursive: true });
fs.copyFileSync(srcPath, dstPath);

const size = (fs.statSync(dstPath).size / 1024 / 1024).toFixed(2);
console.log(`✅ sct-core prebuilt: ${config.libName} -> ${dstDir} (${size} MB)`);
