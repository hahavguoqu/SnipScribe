param([switch]$Disable)
$ErrorActionPreference = 'Stop'
$registryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if ($Disable) {
    Remove-ItemProperty -LiteralPath $registryPath -Name 'SnipScribe' -ErrorAction SilentlyContinue
} else {
    New-Item -Path $registryPath -Force | Out-Null
    $launcher = Join-Path $PSScriptRoot 'Start.vbs'
    $command = '"' + $env:WINDIR + '\System32\wscript.exe" "' + $launcher + '" --background'
    New-ItemProperty -LiteralPath $registryPath -Name 'SnipScribe' -Value $command -PropertyType String -Force | Out-Null
}
