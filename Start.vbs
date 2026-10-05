Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
Set processEnv = shell.Environment("Process")
processEnv("UV_CACHE_DIR") = root & "\.uv-cache"
processEnv("UV_PYTHON_INSTALL_DIR") = root & "\runtime"
processEnv("TEMP") = root & "\temp"
processEnv("TMP") = root & "\temp"
shell.CurrentDirectory = root
uv = "uv"
If fso.FileExists(root & "\tools\uv.exe") Then uv = Chr(34) & root & "\tools\uv.exe" & Chr(34)
shell.Run uv & " run --frozen --no-sync python launch.py", 0, False
