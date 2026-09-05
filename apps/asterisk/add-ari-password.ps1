# Aggiunge SOLO la chiave ari-password al Secret esistente (non tocca SIP/AMI).
$ErrorActionPreference = 'Stop'
$env:KUBECONFIG = 'C:\Users\Gohul\k3s-homelab\kubeconfig'
$existing = kubectl -n asterisk get secret asterisk-sip -o json | ConvertFrom-Json
if ($existing.data.PSObject.Properties.Name -contains 'ari-password') {
  Write-Host "ari-password gia' presente — nessuna modifica."
  exit 0
}
$ari = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 28 | ForEach-Object { [char]$_ })
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($ari))
$patchFile = Join-Path $env:TEMP 'asterisk-ari-password-patch.json'
[System.IO.File]::WriteAllText($patchFile, '[{"op":"add","path":"/data/ari-password","value":"' + $b64 + '"}]')
kubectl -n asterisk patch secret asterisk-sip --type=json --patch-file $patchFile
Set-Content -Path (Join-Path $PSScriptRoot '.ari-secret.local') -Value $ari -Encoding ASCII
Write-Host "ari-password aggiunto. Salvato in .ari-secret.local (gitignored)."
Write-Host "Poi: kubectl -n asterisk rollout restart deploy/asterisk"
