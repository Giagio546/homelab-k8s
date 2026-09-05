# Aggiunge sip-300-password al Secret esistente (non tocca SIP 100/200).
$ErrorActionPreference = 'Stop'
$env:KUBECONFIG = 'C:\Users\Gohul\k3s-homelab\kubeconfig'
$pass300 = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
$ns = 'asterisk'
$tmp = Join-Path $env:TEMP 'asterisk-sip-patch.json'
# read existing, merge key via kubectl patch literal is awkward — recreate from current + new key
$p100 = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n $ns get secret asterisk-sip -o jsonpath='{.data.sip-100-password}')))
$p200 = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n $ns get secret asterisk-sip -o jsonpath='{.data.sip-200-password}')))
$ami = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n $ns get secret asterisk-sip -o jsonpath='{.data.ami-secret}')))
$ari = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n $ns get secret asterisk-sip -o jsonpath='{.data.ari-password}')))
$tpl = Join-Path $PSScriptRoot 'pjsip.conf.template'
kubectl -n $ns create secret generic asterisk-sip `
  --from-literal=sip-100-password=$p100 `
  --from-literal=sip-200-password=$p200 `
  --from-literal=sip-300-password=$pass300 `
  --from-literal=ami-secret=$ami `
  --from-literal=ari-password=$ari `
  --from-file=pjsip.conf.template=$tpl `
  --dry-run=client -o yaml | kubectl apply -f -
Write-Host "sip-300-password set (baresip). Length=$($pass300.Length)"
Add-Content -Path (Join-Path (Split-Path $env:KUBECONFIG) 'asterisk-sip-credentials.txt') -Value "`nBaresip/cam ext 300 pass: $pass300"
