@echo off
REM ZipForge 打包脚本（Windows）
REM 用法：双击本文件，或在命令行执行 build_exe.bat
REM 依赖：pip install pyinstaller

setlocal
cd /d "%~dp0"

echo [1/2] 正在确保 PyInstaller 已安装...
python -m pip install -U pyinstaller
if errorlevel 1 (
    echo 安装 PyInstaller 失败，请手动执行：python -m pip install pyinstaller
    pause
    exit /b 1
)

REM 图标（方案 10「霓虹 ZF」）：若缺失则用脚本即时生成
if not exist "assets\icon_zf_neon.ico" (
    echo 生成程序图标...
    python tools\make_icon.py
)

echo [2/2] 正在打包 ZipForge.exe（单文件 / 无控制台窗口）...
python -m PyInstaller zipforge.py --onefile --windowed --name ZipForge ^
    --paths src ^
    --icon "assets\icon_zf_neon.ico" ^
    --add-data "vendor/engine-x64;vendor/engine-x64" ^
    --add-data "assets;assets" ^
    --distpath dist --workpath build --clean

if errorlevel 1 (
    echo 打包失败，请查看上方日志。
    pause
    exit /b 1
)

echo.
echo 打包完成！可执行文件位于：dist\ZipForge.exe
pause
