# Asterisk (citofono SIP + video)

PBX minimo: squillo citofono → chiamata in arrivo su Linphone (ext **100**) con **video live** da Frigate `cam_130_h264`.

## Deploy (Argo CD + git push)

Git push e sync Argo li fa **Filippo** (niente `kubectl apply` da agent sul live cluster).

1. Commit + push di `apps/asterisk` (questo path).
2. Una tantum sul cluster, **prima** del sync che porta il sidecar:
   - Se Secret nuovo: `.\create-secret.ps1` (crea NS + Secret con SIP + AMI + ARI).
   - Se Secret SIP/AMI gia' esiste: **`.\add-ari-password.ps1`** (aggiunge solo `ari-password`, non rigenera SIP).
3. Sync Application Argo `asterisk` (path `apps/asterisk`). Se auto-sync era stato tolto in prova, riabilitalo dopo il push.
4. Non serve `kubectl apply -k` se Argo synca da git.

### Secret `asterisk-sip` — chiavi

| Key | Uso |
|-----|-----|
| `sip-100-password` | Linphone ext 100 |
| `sip-200-password` | Endpoint citofono 200 |
| `ami-secret` | AMI user `ha` (HA originate legacy) |
| `ari-password` | ARI user `citofono` (sidecar video) |
| `pjsip.conf.template` | Template montato nel pod |

**Non** commitare password. File locali `.ami-secret.local` / `.ari-secret.local` sono gitignored.

## Endpoints

| Ext / porta | Uso |
|-------------|-----|
| 100 | Linphone (Android Filippo) — codec audio + **h264** |
| 200 | Caller citofono |
| 201 | Test ring audio verso 100 |
| AMI 5038 | HA / debug |
| ARI HTTP `127.0.0.1:8088` | Solo localhost sul nodo (sidecar) |
| Ring helper `192.168.8.132:8099` | `GET/POST /ring`, `GET /health` |

## Video path

1. **Frigate go2rtc** (hostPath `/opt/frigate/config/config.yml` sul nodo `k3s`) — **non** e' in questo repo; applicarlo a mano sul host / nel volume Frigate **prima** di testare il video:

```yaml
go2rtc:
  streams:
    # ... cam_130 / cam_130_sub esistenti ...
    cam_130_h264:
      # substream → H264 ~1280x720 (adatto a SIP; evita 4K sul main)
      - ffmpeg:cam_130_sub#video=h264#hardware
```

Backup del config prima di editare. Poi restart Frigate (o reload se supportato).

Verifica RTSP (dal pod Frigate o LAN verso ClusterIP `10.43.38.49:8554`):

```text
ffprobe -rtsp_transport tcp rtsp://127.0.0.1:8554/cam_130_h264
# atteso: codec_name=h264, ~1280x720
```

2. **Sidecar `citofono-video`** (stesso pod hostNetwork di Asterisk):
   - Abilita HTTP+ARI su `127.0.0.1:8088`, user ARI `citofono`.
   - Stasis app `citofono`: originate `PJSIP/100` con `formats=ulaw,h264`, ExternalMedia H264, `ffmpeg` da `rtsp://10.43.38.49:8554/cam_130_h264` → RTP.
   - HTTP ring: `http://192.168.8.132:8099/ring`

3. **HA** — aggiornare lo shell script (SMB HA, non in questo repo), es. `\\192.168.8.104\config\citofono_ami_originate.py`, per chiamare il helper video invece di AMI Context/Exten. Esempio minimo:

```python
#!/usr/bin/env python3
import urllib.request
import sys
try:
    with urllib.request.urlopen("http://192.168.8.132:8099/ring", timeout=5) as r:
        body = r.read().decode("ascii", "replace")
    print("ok", body)
    raise SystemExit(0)
except Exception as e:
    print(e, file=sys.stderr)
    raise SystemExit(1)
```

Fallback AMI (solo audio / Stasis dopo answer), se serve:

```text
Action: Originate
Channel: PJSIP/100
Application: Stasis
Data: citofono
CallerID: Citofono <200>
Async: true
Timeout: 45000
```

Companion notify: lasciare disabilitato sul ring (solo SIP). Stub door/audio: non toccare.

## Rete

- Pod sul nodo `k3s` con **hostNetwork** (SIP/RTP in LAN).
- Linphone: server `192.168.8.132` (LAN) o `100.76.69.43` (Tailscale), user `100`, transport UDP.
- Porte: **5060** SIP, **10000–10200** RTP (`strictrtp=no` per ExternalMedia), **5038** AMI, **8099** ring HTTP, **8088** ARI solo loopback.

## File in questo directory

| File | Ruolo |
|------|--------|
| `deployment.yaml` | Asterisk + sidecar `citofono-video` |
| `configmap.yaml` | extensions / rtp / http / ari / manager |
| `citofono-ari-configmap.yaml` | Script Python montato in `/app` |
| `citofono_ari.py` | Sorgente dello script (tenere allineato al ConfigMap) |
| `pjsip.conf.template` | Endpoint 100/200 (h264 gia' allowed) |
| `add-ari-password.ps1` | Aggiunge solo `ari-password` al Secret esistente |
| `create-secret.ps1` | Crea Secret completo (rigenera password — solo greenfield) |

Se modifichi `citofono_ari.py`, rigenera l'embedding nel ConfigMap (indentare il file sotto `data.citofono_ari.py: |`) prima del commit.

## Verifica / retest

```powershell
$env:KUBECONFIG = 'C:\Users\Gohul\k3s-homelab\kubeconfig'
kubectl -n asterisk get pods
kubectl -n asterisk exec deploy/asterisk -c asterisk -- asterisk -rx 'http show status'
kubectl -n asterisk exec deploy/asterisk -c asterisk -- asterisk -rx 'ari show users'
kubectl -n asterisk exec deploy/asterisk -c asterisk -- asterisk -rx 'pjsip show endpoints'
kubectl -n asterisk logs deploy/asterisk -c citofono-video --tail=50
# Ring di test (Linphone registrato):
Invoke-WebRequest -Uri http://192.168.8.132:8099/ring -UseBasicParsing
# Oppure MQTT/HA: pubblica su citofono/ring dopo aver aggiornato lo script HA
```

Atteso:
- Pod `2/2 Ready`
- HTTP Asterisk bound `127.0.0.1:8088`, user ARI `citofono`
- Ext 100 `Avail`
- `/ring` → squillo Linphone; in call (o early media) video da portone
- Log sidecar: `StasisStart`, `video bridged`, `starting ffmpeg RTP`

Se squilla ma senza video: controllare `cam_130_h264` playable, log ffmpeg nel sidecar, codec H264 negoziato (`pjsip set logger on` / SDP).

## Prossimi step (fuori scope manifest)

- Early-media / preview video a squillo (gia' tentato via ARI originate + progress)
- Audio bus citofono reale (oggi stub)
- Door open (stub)
