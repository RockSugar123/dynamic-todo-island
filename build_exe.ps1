$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

python -m pip install -r requirements.txt
python -m PyInstaller --clean --noconfirm DynamicTodoIsland.spec
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "sign_local_exe.ps1")
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "create_desktop_shortcut.ps1")

Write-Host "Built: $PSScriptRoot\dist\DynamicTodoIsland.exe"
