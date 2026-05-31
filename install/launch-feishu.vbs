Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = objShell.CurrentDirectory & "\.."
objShell.Run ".venv\Scripts\pythonw.exe scripts\feishu_launcher.pyw", 0, False
