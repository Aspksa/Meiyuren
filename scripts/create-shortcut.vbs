Option Explicit
Dim shell, fs, scriptsDir, appDir, shortcut, desktop, iconPath

Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")

scriptsDir = fs.GetParentFolderName(WScript.ScriptFullName)
appDir = fs.GetParentFolderName(scriptsDir)
desktop = shell.SpecialFolders("Desktop")

If Not fs.FileExists(fs.BuildPath(appDir, "Meiyuren.cmd")) Then
  WScript.Echo "Launcher not found."
  WScript.Quit 1
End If

Set shortcut = shell.CreateShortcut(fs.BuildPath(desktop, "Meiyuren.lnk"))
shortcut.TargetPath = fs.BuildPath(appDir, "Meiyuren.cmd")
shortcut.WorkingDirectory = appDir
iconPath = fs.BuildPath(appDir, "public\assets\icons\meiyuren.ico")
If fs.FileExists(iconPath) Then
  shortcut.IconLocation = iconPath & ",0"
End If
shortcut.Description = "Meiyuren - interactive web avatar"
shortcut.WindowStyle = 1
shortcut.Save
WScript.Echo "Shortcut created: " & shortcut.FullName
