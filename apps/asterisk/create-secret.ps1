# Crea il Secret asterisk-sip (una tantum). Non commitare le password.
$ErrorActionPreference = 'Stop'
$env:KUBECONFIG = 'C:\Users\Gohul\k3s-homelab\kubeconfig'
$pass100 = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
$pass200 = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
$ami     = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
$tpl = Join-Path $PSScriptRoot 'pjsip.conf.template'
kubectl create namespace asterisk --dry-run=client -o yaml | kubectl apply -f -
kubectl -n asterisk create secret generic asterisk-sip `
  --from-literal=sip-100-password=$pass100 `
  --from-literal=sip-200-password=$pass200 `
  --from-literal=ami-secret=$ami `
  --from-file=pjsip.conf.template=$tpl `
  --dry-run=client -o yaml | kubectl apply -f -
Write-Host ""
Write-Host "Linphone user: 100"
Write-Host "Linphone pass: $pass100"
Write-Host "SIP server:    192.168.8.132  (o Tailscale 100.76.69.43)"
Write-Host "AMI secret:    $ami  (per HA originate, dopo)"