$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

$exePath = Join-Path $PSScriptRoot "dist\DynamicTodoIsland.exe"
$certSubject = "CN=Dynamic Todo Island Local"

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Executable not found: $exePath. Run build_exe.ps1 first."
}

$cert = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object { $_.Subject -eq $certSubject -and $_.HasPrivateKey } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if (-not $cert) {
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $certSubject `
        -CertStoreLocation Cert:\CurrentUser\My `
        -KeyUsage DigitalSignature `
        -FriendlyName "Dynamic Todo Island Local Code Signing"
}

$rootCertPath = "Cert:\CurrentUser\Root\$($cert.Thumbprint)"
if (-not (Test-Path -LiteralPath $rootCertPath)) {
    $exportPath = Join-Path $env:TEMP "DynamicTodoIslandLocal.cer"
    Export-Certificate -Cert $cert -FilePath $exportPath | Out-Null
    Import-Certificate -FilePath $exportPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
    Import-Certificate -FilePath $exportPath -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
    Remove-Item -LiteralPath $exportPath -Force
}

$signature = Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert
if ($signature.Status -ne "Valid") {
    throw "Signing failed: $($signature.Status) - $($signature.StatusMessage)"
}

Write-Host "Signed executable with: $($cert.Subject)"
