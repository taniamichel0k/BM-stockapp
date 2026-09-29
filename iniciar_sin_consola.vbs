Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Users\Tania Michel\Documents\App-Stock"
WshShell.Run chr(34) & "c:\Users\Tania Michel\Documents\App-Stock\iniciar_app.bat" & chr(34), 0, False
