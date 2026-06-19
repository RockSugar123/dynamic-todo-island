@echo off
cd /d "%~dp0"
if exist "dist\DynamicTodoIsland.exe" (
    start "" "dist\DynamicTodoIsland.exe"
) else (
    start "" pythonw app.py
)
