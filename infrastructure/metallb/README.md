\# MetalLB notes



Cluster Talos single-node control-plane.



Talos/Kubernetes adds:



`node.kubernetes.io/exclude-from-external-load-balancers`



MetalLB speaker must be configured with:



`--ignore-exclude-lb`



Otherwise L2 VIPs are assigned to Services but not announced properly.



Current VIP used by Traefik:



`192.168.8.20`

