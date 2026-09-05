# Asterisk (citofono SIP + video ConfBridge)

Squillo citofono → Linphone **100** + camera softphone **baresip 300** in **ConfBridge** (video H264 da Frigate `cam_130_h264`).

## Deploy (Argo — Filippo fa push/sync)

1. Commit + push `apps/asterisk`.
2. Secret `asterisk-sip` keys richieste:
   - `sip-100-password`, `sip-200-password`, `sip-300-password` (baresip)
   - `ami-secret`, `ari-password`
   - `pjsip.conf.template` (file nel Secret)
3. Se Secret esiste già: aggiungi solo `sip-300-password` con `.\add-sip300-password.ps1` (non rigenerare 100).
4. Sync Argo app `asterisk`.
5. Frigate go2rtc deve esporre `cam_130_h264` (già sul host se fatto in sessione precedente).

## Flusso

1. HA / MQTT `citofono/ring` → `http://192.168.8.132:8099/ring`
2. Helper AMI origina `PJSIP/100` e `PJSIP/300` in ConfBridge `1`
3. baresip (answermode=auto) entra in conference mandando video RTSP
4. Linphone vede video nella call (softmix/SFU ConfBridge)

## HA

`\\192.168.8.104\config\citofono_ami_originate.py` deve chiamare `/ring` (già impostato).

## Verifica

```powershell
$env:KUBECONFIG='C:\Users\Gohul\k3s-homelab\kubeconfig'
kubectl -n asterisk get pods
kubectl -n asterisk exec deploy/asterisk -c asterisk -- asterisk -rx 'pjsip show contacts'
# atteso: 100 (Linphone) e 300 (baresip) Avail
Invoke-WebRequest http://192.168.8.132:8099/ring -UseBasicParsing
```

## Note

- Vecchio path ARI ExternalMedia (`citofono-video`) rimosso: `simple_bridge` non inoltrava video.
- baresip installa pacchetti al boot del container (primo avvio lento ~1 min).
