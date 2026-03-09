param(
    [int]$Port = 8000,
    [string]$Ip = ""
)

$ErrorActionPreference = "Stop"

if (-not $Ip) {
    $ipConfig = Get-NetIPConfiguration | Where-Object { $_.IPv4Address -and $_.IPv4DefaultGateway } | Select-Object -First 1
    if ($ipConfig -and $ipConfig.IPv4Address) {
        $Ip = $ipConfig.IPv4Address.IPAddress
    }
}

if (-not $Ip) {
    throw "Khong tim thay IP LAN. Hay truyen tham so -Ip, vi du: .\\run_lan.ps1 -Ip 192.168.2.175"
}

$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,$Ip"
$env:QR_PUBLIC_BASE_URL = "http://$Ip`:$Port"

$pythonExe = Join-Path $PSScriptRoot ".venv\\Scripts\\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

Write-Host "LAN URL: http://$Ip`:$Port" -ForegroundColor Green
Write-Host "QR base: $env:QR_PUBLIC_BASE_URL" -ForegroundColor Green
Write-Host "Nhan Ctrl+C de dung server." -ForegroundColor Yellow

& $pythonExe manage.py runserver 0.0.0.0:$Port
