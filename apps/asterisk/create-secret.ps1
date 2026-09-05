# Crea/aggiorna il Secret asterisk-sip (una tantum). Non commitare le password.
# Non rigenerare se il Secret esiste gia' con SIP passwords: usa add-ari-password.ps1.
$ErrorActionPreference = 'Stop'
$env:KUBECONFIG = 'C:\Users\Gohul\k3s-homelab\kubeconfig'
$pass100 = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
$pass200 = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
$ami     = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
$ari     = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 28 | ForEach-Object { [char]$_ })
$tpl = Join-Path $PSScriptRoot 'pjsip.conf.template'
kubectl create namespace asterisk --dry-run=client -o yaml | kubectl apply -f -
kubectl -n asterisk create secret generic asterisk-sip `
  --from-literal=sip-100-password=$pass100 `
  --from-literal=sip-200-password=$pass200 `
  --from-literal=ami-secret=$ami `
  --from-literal=ari-password=$ari `
  --from-file=pjsip.conf.template=$tpl `
  --dry-run=client -o yaml | kubectl apply -f -
Set-Content -Path (Join-Path $PSScriptRoot '.ami-secret.local') -Value $ami -Encoding ASCII
Set-Content -Path (Join-Path $PSScriptRoot '.ari-secret.local') -Value $ari -Encoding ASCII
Write-Host ""
Write-Host "Linphone user: 100"
Write-Host "Linphone pass: $pass100"
Write-Host "SIP server:    192.168.8.132  (o Tailscale 100.76.69.43)"
Write-Host "AMI secret:    $ami"
Write-Host "ARI password:  $ari  (sidecar citofono-video)"
Write-Host "Saved locally: .ami-secret.local .ari-secret.local (gitignored)"
