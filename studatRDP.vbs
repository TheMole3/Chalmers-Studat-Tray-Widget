Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = "C:\Users\hugom\Documents\GitHub\chalmersAuth"
objShell.Run "cmd /c python studatRDP.py", 0, False
