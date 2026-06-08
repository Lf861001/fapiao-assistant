$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

$appName = "发票递交助手"
$sourceRoot = Join-Path $PSScriptRoot "发票递交助手"
$installRoot = Join-Path $env:LOCALAPPDATA $appName
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$appName.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) $appName
$startMenuShortcut = Join-Path $startMenuDir "$appName.lnk"

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    throw "安装文件不完整，缺少 $appName 程序目录。"
}

if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot "*") -Destination $installRoot -Recurse -Force

$exePath = Join-Path $installRoot "$appName.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "安装失败，未找到 $appName.exe。"
}

$shell = New-Object -ComObject WScript.Shell

$desktop = $shell.CreateShortcut($desktopShortcut)
$desktop.TargetPath = $exePath
$desktop.WorkingDirectory = $installRoot
$desktop.IconLocation = $exePath
$desktop.Save()

New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
$startMenu = $shell.CreateShortcut($startMenuShortcut)
$startMenu.TargetPath = $exePath
$startMenu.WorkingDirectory = $installRoot
$startMenu.IconLocation = $exePath
$startMenu.Save()

[System.Windows.MessageBox]::Show("发票递交助手已安装完成。桌面快捷方式已创建。", "安装完成", "OK", "Information") | Out-Null
