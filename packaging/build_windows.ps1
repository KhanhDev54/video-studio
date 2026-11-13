# Đóng gói Video Studio thành thư mục dist\VideoStudio (chạy trên Windows, trong thư mục repo):
#   py -3 -m pip install -r requirements.txt pyinstaller
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --clean --windowed --name VideoStudio `
  --collect-submodules edge_tts --paths . `
  --add-data "video_studio\assets;video_studio\assets" --hidden-import PySide6.QtSvg `
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets `
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.Qt3DCore `
  packaging\launcher.py
Copy-Item -Recurse -Force examples dist\VideoStudio\examples
Copy-Item -Force packaging\HUONG_DAN.txt dist\VideoStudio\HUONG_DAN.txt
