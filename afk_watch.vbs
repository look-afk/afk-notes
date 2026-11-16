Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
pyw = "C:\Users\Zafar\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
script = "C:\Users\Zafar\afk.py"
If fso.FileExists(pyw) And fso.FileExists(script) Then
  sh.Run """" & pyw & """ """ & script & """ --watch", 0, False
End If
