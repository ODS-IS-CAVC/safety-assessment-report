$ErrorActionPreference = "Stop"

$pythonExe = "C:\Users\divp\AppData\Local\Programs\Python\Python312\python.exe"

# Build JP literals in ASCII-safe form so Windows PowerShell does not mojibake UTF-8 source.
$jpSheet = [string]::Concat([char[]](0x96C6, 0x8A08, 0x8868))
$mobilityDx = [string]::Concat([char[]](0x30E2, 0x30D3, 0x30EA, 0x30C6, 0x30A3))

# Inclusive logs root. Real files live under car_week/csv/*.csv.
$logsRoot = "\\192.168.16.5\Public\tmp_" + $mobilityDx + "DX_HDD"
$routesGlob = "**/csv/*.csv"
$logsGlobForMap = "**/csv/*.csv"
$legacySheet = "AllPoints_1018"

# Optional manifest to avoid rescanning the UNC tree every run.
# One CSV/TXT path per line. Leave blank or point to a non-existent file to fall back to glob scanning.
$logsManifest = ".\pipeline_out\_cache\logs_manifest.txt"
$buildManifestIfMissing = $true
$rebuildCsvOnlyManifest = $true

# Excel inputs
$jpExcel = ".\sheet_v2.xlsx"
$legacyExcel = ".\route_nearmiss_analysis_with_dx_and_unknown_GROUPED_v12_all1018.xlsx"
if (-not (Test-Path $legacyExcel)) {
  $legacyExcel = ".\AllPoints_1018.xlsx"
}

$allowlistScript = ".\make_allowlist_carweek_from_excel.py"
$exposureScript = ".\E1A_ab_dist_scan_v3_1_carweek_exposure.py"
$roadgroupExposureScript = ".\make_exposure_by_excel_routegroup_v1.py"

# Optional route export
$refreshExposure = $true
$exportRoutes = $true
$routesMaxPoints = 20000

$outHtml = ".\pipeline_out\nearmiss_points_map_v67_richui_both_excels.html"
$cacheDir = ".\pipeline_out\_cache"
$routesOutDir = ".\pipeline_out\routes_out"
$exposureOutDir = ".\pipeline_out\exposure_out"
$allowlistOut = Join-Path $exposureOutDir "allowlist_carweek.txt"

$osmLabelCache = ".\osm_label_cache.json"
$osmReverseCache = ".\osm_reverse_cache.json"
$osmOverpassCache = ".\osm_overpass_cache.json"
$osmFetchMissing = $true
$osmMaxRequests = 800
$osmSleep = 1.0

New-Item -ItemType Directory -Force -Path ".\pipeline_out" | Out-Null
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
New-Item -ItemType Directory -Force -Path $exposureOutDir | Out-Null

function Get-ManifestStats($path) {
  $stats = [ordered]@{
    Total = 0
    Csv = 0
    Txt = 0
  }
  if (-not $path -or -not (Test-Path $path)) {
    return [pscustomobject]$stats
  }
  Get-Content -LiteralPath $path | ForEach-Object {
    $line = (($_ -replace [char]0xFEFF, "").Trim())
    if (-not $line -or $line.StartsWith("#") -or $line.StartsWith(";")) {
      return
    }
    $stats.Total += 1
    $ext = [System.IO.Path]::GetExtension($line).ToLowerInvariant()
    if ($ext -eq ".csv") { $stats.Csv += 1 }
    elseif ($ext -eq ".txt") { $stats.Txt += 1 }
  }
  return [pscustomobject]$stats
}

$shouldBuildManifest = $false
if ($logsManifest) {
  if (-not (Test-Path $logsManifest)) {
    $shouldBuildManifest = $buildManifestIfMissing
  } elseif ($rebuildCsvOnlyManifest) {
    $manifestStats = Get-ManifestStats $logsManifest
    if ($manifestStats.Total -gt 0 -and $manifestStats.Txt -eq 0) {
      Write-Host "[prep] Existing logs manifest is csv-only ($($manifestStats.Total) files). Rebuilding with csv+txt..." -ForegroundColor Yellow
      $shouldBuildManifest = $true
    }
  }
}

if ($shouldBuildManifest) {
  Write-Host "[prep] Building logs manifest..." -ForegroundColor Cyan
  $manifestDir = Split-Path -Parent $logsManifest
  if ($manifestDir) {
    New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
  }
  $manifestLines = Get-ChildItem -LiteralPath $logsRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
      $ext = $_.Extension.ToLowerInvariant()
      ($ext -eq ".csv" -or $ext -eq ".txt") -and ($_.FullName -match "\\csv\\")
    } |
    Sort-Object FullName |
    Select-Object -ExpandProperty FullName
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines((Resolve-Path -LiteralPath $manifestDir | ForEach-Object { Join-Path $_ $([System.IO.Path]::GetFileName($logsManifest)) }), $manifestLines, $utf8NoBom)
  Write-Host ("[prep] Logs manifest ready: {0} files" -f @($manifestLines).Count) -ForegroundColor Green
}

if ($refreshExposure) {
  Write-Host "[1/4] Building allowlist from Excel..." -ForegroundColor Cyan
  $allowArgs = @(
    $allowlistScript,
    "--excel", $jpExcel,
    "--sheet", $jpSheet,
    "--old-excel", $legacyExcel,
    "--old-sheet", $legacySheet,
    "--out", $allowlistOut
  )
  & $pythonExe @allowArgs

  Write-Host "[2/4] Recomputing exposure totals..." -ForegroundColor Cyan
  $exposureArgs = @(
    $exposureScript,
    "--root", $logsRoot,
    "--glob", $routesGlob,
    # --allowlist-carweek intentionally removed: include ALL car_weeks on the drive
    # so that zero-event weeks count toward the exposure denominator (gives accurate rates).
    "--label-cache", $osmLabelCache,
    "--outdir", $exposureOutDir,
    "--summarize-all"
  )
  if ($logsManifest -and (Test-Path $logsManifest)) {
    $exposureArgs += @("--logs-manifest", $logsManifest)
  }
  & $pythonExe @exposureArgs

  $totalsCarweekLabel = Join-Path $exposureOutDir "totals_by_carweek_label.csv"
  $totalsLabel = Join-Path $exposureOutDir "totals_by_label.csv"
  if ((Test-Path $totalsCarweekLabel) -and (Test-Path $totalsLabel)) {
    Write-Host "[3/4] Building road-group exposure rollups..." -ForegroundColor Cyan
    $roadgroupArgs = @(
      $roadgroupExposureScript,
      "--excel", $legacyExcel,
      "--sheet", $legacySheet,
      "--totals_carweek_label", $totalsCarweekLabel,
      "--totals_label", $totalsLabel,
      "--outdir", $exposureOutDir
    )
    & $pythonExe @roadgroupArgs
  }
}

if ($exportRoutes) {
  New-Item -ItemType Directory -Force -Path $routesOutDir | Out-Null
  Write-Host "[4/4] Exporting routes (routes_by_*.geojson)..." -ForegroundColor Cyan
  $routeArgs = @(
    ".\E1A_ab_dist_scan_v3_1_carweek_exposure.py",
    "--root", $logsRoot,
    "--glob", $routesGlob,
    "--allowlist-carweek", $allowlistOut,
    "--routes-only",
    "--routes-out", $routesOutDir,
    "--routes-max-points", $routesMaxPoints,
    "--outdir", ".\pipeline_out\ab_out"
  )
  if ($logsManifest -and (Test-Path $logsManifest)) {
    $routeArgs += @("--logs-manifest", $logsManifest)
  }
  & $pythonExe @routeArgs
}

Write-Host "[final] Generating v67 rich UI map (both excels)..." -ForegroundColor Cyan

$generatorArgs = @(
  ".\generate_nearmiss_map_v67_richui_both_excels.py",
  "--jp-excel", $jpExcel,
  "--jp-sheet", $jpSheet,
  "--legacy-excel", $legacyExcel,
  "--legacy-sheet", $legacySheet,
  "--logs-root", $logsRoot,
  "--logs-glob", $logsGlobForMap,
  "--cache-dir", $cacheDir,
  "--routes-dir", $routesOutDir,
  "--osm-label-cache", $osmLabelCache,
  "--osm-reverse-cache", $osmReverseCache,
  "--osm-overpass-cache", $osmOverpassCache,
  "--osm-max-requests", $osmMaxRequests,
  "--osm-sleep", $osmSleep,
  "--out", $outHtml
)

if ($logsManifest -and (Test-Path $logsManifest)) {
  $generatorArgs += @("--logs-manifest", $logsManifest)
}
if ($osmFetchMissing) {
  $generatorArgs += "--osm-fetch-missing"
}

& $pythonExe @generatorArgs

Write-Host "Done: $outHtml" -ForegroundColor Green
