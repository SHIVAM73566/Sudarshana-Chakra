$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('C:\Users\ravit\OneDrive\Desktop\Sudarshana Chakra.lnk')
$Shortcut.TargetPath = 'D:\TiTech Prabha Solution\Sudarshana AI\Sudarshana AI\Sudarshana-AI---Lite-main\Sudarshana-AI---Lite-main\.venv\Scripts\pythonw.exe'
$Shortcut.Arguments = '"D:\TiTech Prabha Solution\Sudarshana AI\Sudarshana AI\Sudarshana-AI---Lite-main\Sudarshana-AI---Lite-main\main.py"'
$Shortcut.WorkingDirectory = 'D:\TiTech Prabha Solution\Sudarshana AI\Sudarshana AI\Sudarshana-AI---Lite-main\Sudarshana-AI---Lite-main'
$Shortcut.WindowStyle = 7
$Shortcut.Description = 'Launch Sudarshana Chakra'
if ('D:\TiTech Prabha Solution\Sudarshana AI\Sudarshana AI\Sudarshana-AI---Lite-main\Sudarshana-AI---Lite-main\assets\Sudarshana_Lite_Logo.ico') { $Shortcut.IconLocation = 'D:\TiTech Prabha Solution\Sudarshana AI\Sudarshana AI\Sudarshana-AI---Lite-main\Sudarshana-AI---Lite-main\assets\Sudarshana_Lite_Logo.ico,0' }
$Shortcut.Save()