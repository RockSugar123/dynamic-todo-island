$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

$exePath = Join-Path $PSScriptRoot "dist\DynamicTodoIsland.exe"
$iconPath = Join-Path $PSScriptRoot "icon.ico"

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Executable not found: $exePath. Run build_exe.ps1 first."
}

if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Icon not found: $iconPath"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Dynamic Todo Island.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = $iconPath
$shortcut.Description = "Dynamic Todo Island"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath"
