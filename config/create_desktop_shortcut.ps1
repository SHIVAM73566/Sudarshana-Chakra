# Creates a Desktop shortcut for Sudarshana Chakra on the current machine.
# Portable: all paths are resolved relative to the repository root.
$Root = Split-Path -Parent $PSScriptRoot

$PythonW = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $PythonW)) { $PythonW = Join-Path $Root ".venv\Scripts\python.exe" }
if (-not (Test-Path $PythonW)) { $PythonW = "pythonw" }

$Main = Join-Path $Root "main.py"
$Icon = Join-Path $Root "assets\favicon.ico"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) "Sudarshana Chakra.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PythonW
$Shortcut.Arguments = '"' + $Main + '"'
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 7
$Shortcut.Description = 'Launch Sudarshana Chakra'
if (Test-Path $Icon) { $Shortcut.IconLocation = "$Icon,0" }
$Shortcut.Save()

Write-Host "Desktop shortcut created: $ShortcutPath"