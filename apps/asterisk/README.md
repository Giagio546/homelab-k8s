# Asterisk (citofono SIP)

PBX minimo: squillo citofono → chiamata in arrivo su Linphone (ext 100).

## Deploy (Argo CD)
1. Commit + push di `apps/asterisk` (e opzionale `argocd/asterisk-app.yaml`).
2. Una tantum sul cluster: `.\create-secret.ps1` (crea NS + Secret con password SIP).
3. Crea/sync l'Application Argo `asterisk` (path `apps/asterisk`) — es. `kubectl apply -f argocd/asterisk-app.yaml` se non c’è già un app-of-apps.
4. Non usare `kubectl apply -k` sull’app: synca Argo.

## Endpoints
| Ext | Uso |
|-----|-----|
| 100 | Linphone (Android di Filippo) |
| 200 | Caller citofono (AMI Originate) |
| 201 | Test ring verso 100 |

## Rete
- Pod sul nodo `k3s` con **hostNetwork** (SIP/RTP in LAN).
- Linphone: server `192.168.8.132` (LAN) o `100.76.69.43` (Tailscale), user `100`, transport UDP.
- Porte: **5060** SIP, **10000–10100** RTP, **5038** AMI.

## Verifica
```
kubectl -n asterisk get pods
kubectl -n asterisk exec deploy/asterisk -- asterisk -rx 'pjsip show endpoints'
```

## Prossimi step
- HA `citofono/ring` → AMI Originate → 100
- Video cam portone (RTSP / go2rtc) nella call
- Companion notify = solo fallback
- Door / audio bus = stub