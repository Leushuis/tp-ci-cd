# TP 3 — Fiabilité, ressources et montée en charge

Une application en production doit signaler son état, consommer des ressources prévisibles, conserver ses données et encaisser la charge. Ce TP configure chacun de ces points.

## Les fichiers

- [`ready.yaml`](./ready.yaml) crée le Deployment `web` (2 réplicas nginx) avec une readiness probe HTTP, et le Service `web`.
- [`liveness.yaml`](./liveness.yaml) crée le Pod `zombie`. Ce Pod supprime son fichier `/tmp/healthy` au bout de 30 s, ce qui fait échouer sa liveness probe.
- [`oom.yaml`](./oom.yaml) crée le Pod `gourmand`, qui tente d'allouer 250 Mo avec une limite mémoire de 100 Mi.
- [`redis-pvc.yaml`](./redis-pvc.yaml) crée le PersistentVolumeClaim `redis-data` (1 Gi, RWO) et un Deployment `redis` qui stocke ses données dessus.

L'application `php-apache` et son HPA sont créés en ligne de commande (voir la section 4).

## Prérequis

Le cluster kind tourne dans le conteneur `kind-box`, et `k` est un alias de `kubectl`. Le TP se déroule dans un namespace dédié :

```bash
docker exec -it -w /work/tp-k8s/tp3 kind-box bash
k create ns tp3 && k config set-context --current --namespace=tp3
```

## 1. Probes

Le kubelet interroge régulièrement les conteneurs pour connaître leur état. Une probe peut être un `httpGet` (réussie pour un code entre 200 et 399), un `tcpSocket` ou un `exec` (réussie si la commande renvoie 0).

| Probe            | Question posée               | En cas d'échec                       |
|------------------|------------------------------|--------------------------------------|
| `readinessProbe` | Peux-tu recevoir du trafic ? | Pod retiré des endpoints du Service  |
| `livenessProbe`  | Es-tu encore vivant ?        | Conteneur redémarré                  |
| `startupProbe`   | As-tu fini de démarrer ?     | Les deux autres probes attendent     |

### Readiness

```bash
k apply -f ready.yaml
k get pods                                  # READY 0/1, STATUS Running
k describe svc web                          # Endpoints vide
k get events --sort-by=.lastTimestamp | grep -i readiness
```

Avec `path: /ready`, nginx répond 404. Les Pods tournent (`Running`, aucun redémarrage), mais ils ne sont pas prêts (`0/1`). Le Service n'a alors aucun endpoint et ne route aucun trafic. Avec `path: /`, la version actuelle du fichier, les Pods passent à `1/1` et apparaissent dans les endpoints.

La readiness permet les déploiements sans coupure : un Pod ne reçoit du trafic que lorsqu'il est prêt, et un rolling update n'arrête l'ancien Pod qu'une fois le nouveau prêt.

### Liveness

```bash
k apply -f liveness.yaml
k get pods zombie -w                        # RESTARTS augmente
k describe pod zombie | tail -15            # Unhealthy, Killing
```

Le fichier disparaît à 30 s. La probe échoue 3 fois d'affilée (`failureThreshold`), et le kubelet tue le conteneur. Le premier redémarrage n'arrive qu'à environ 75 s, et non 45 s. Le kubelet envoie d'abord SIGTERM, puis il attend `terminationGracePeriodSeconds` (30 s) avant d'envoyer SIGKILL. Or `sh` en PID 1 ignore SIGTERM.

C'est le **conteneur** qui redémarre, pas le Pod : l'`AGE` du Pod ne repart pas à zéro.

Une liveness probe ne doit jamais dépendre d'une base de données ou d'un service externe. Si celui-ci tombe, tous les Pods redémarrent en boucle et la panne s'aggrave.

## 2. Requests et limits

| | requests | limits |
|---|---|---|
| Utilisé par | le scheduler, au placement | le noyau, à l'exécution |
| Dépassement CPU | — | ralenti (throttling) |
| Dépassement mémoire | — | tué (OOMKilled) |

```bash
k apply -f oom.yaml
k get pods gourmand -w                              # OOMKilled → CrashLoopBackOff
k describe pod gourmand | grep -A 4 "Last State"    # Reason: OOMKilled, Exit Code: 137
k get pod gourmand -o jsonpath='{.status.qosClass}'; echo   # Burstable
```

Le code de sortie 137 vaut 128 + 9 (SIGKILL), envoyé par l'OOM killer du noyau. `CrashLoopBackOff` est un symptôme, pas une cause : Kubernetes espace les redémarrages de façon exponentielle (10 s, 20 s, 40 s… jusqu'à 5 min). La cause se lit dans `Last State` ou avec `k logs <pod> --previous`.

La classe QoS détermine l'ordre d'éviction quand un nœud manque de mémoire :

| Classe | Condition |
|---|---|
| `BestEffort` | aucune request ni limit (expulsé en premier) |
| `Burstable` | au moins une request, requests ≠ limits |
| `Guaranteed` | requests = limits pour le CPU et la mémoire, sur tous les conteneurs (expulsé en dernier) |

## 3. Volumes persistants

Un PersistentVolumeClaim (PVC) demande du stockage. La StorageClass (`standard`, provisioner `rancher.io/local-path` dans kind) crée automatiquement le PersistentVolume (PV) correspondant.

```bash
k get storageclass
k apply -f redis-pvc.yaml
k get pvc,pv                                     # Bound
k exec deploy/redis -- redis-cli INCR visites
k exec deploy/redis -- redis-cli INCR visites
k delete pod -l app=redis                        # le Pod est recréé…
k exec deploy/redis -- redis-cli GET visites     # … et renvoie toujours 2
```

Quelques points à noter :
- **Le PV est créé au premier Pod.** Le mode `WaitForFirstConsumer` de local-path attend de connaître le nœud du Pod. Le PVC reste `Pending` tant qu'aucun Pod ne l'utilise.
- **`strategy: Recreate`.** Un volume `ReadWriteOnce` ne peut pas être monté par deux Pods sur deux nœuds. L'ancien Pod est donc supprimé avant la création du nouveau.
- **`--appendonly yes`.** Redis écrit ses données sur `/data`. Sans cette option, il les garderait uniquement en mémoire.
- **`Reclaim policy: Delete`.** Supprimer le PVC supprime le PV et les données.
- **StatefulSet.** Pour une base répliquée, où chaque réplica a son propre volume, on utilise un StatefulSet.

## 4. Autoscaling horizontal (HPA)

Le HPA ajuste le nombre de réplicas d'après les métriques de metrics-server :

```bash
k apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
k -n kube-system patch deploy metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
k -n kube-system rollout status deploy metrics-server
k top nodes
```

L'option `--kubelet-insecure-tls` désactive la vérification du certificat auto-signé du kubelet. Elle est acceptable dans kind, jamais en production.

```bash
k create deploy php-apache --image=registry.k8s.io/hpa-example --port=80
k set resources deploy php-apache --requests=cpu=200m --limits=cpu=500m
k expose deploy php-apache --port=80
k autoscale deploy php-apache --cpu=50% --min=1 --max=6
```

La cible de 50 % est calculée par rapport à la **request** CPU (ici, 100m par Pod). Sans request, le HPA affiche `<unknown>`. Dans kubectl 1.33, `--cpu-percent` est déprécié au profit de `--cpu=50%`.

Pour observer (terminal 2) et générer de la charge (terminal 1) :

```bash
k get hpa php-apache -w
k run load --rm -it --image=busybox:1.36 --restart=Never -- \
  sh -c 'while sleep 0.01; do wget -q -O- http://php-apache; done'
```

Le HPA calcule `réplicas souhaités = réplicas actuels × (CPU mesuré / CPU cible)`. Résultat observé :

```
New size: 4   ← 1 → 4 (montée limitée par défaut à +4 Pods ou ×2 toutes les 15 s)
New size: 5
New size: 6   ← maximum atteint, CPU toujours à ~71 % (le HPA voudrait ~9 réplicas)
```

Le nœud kind n'a que 2 CPU. Le HPA ajoute des Pods, pas des machines : c'est le rôle du Cluster Autoscaler.

Après l'arrêt de la charge, le CPU retombe à 0 % immédiatement, mais les réplicas ne diminuent qu'au bout de **5 minutes**. C'est la fenêtre de stabilisation de la réduction : le HPA applique la plus haute recommandation des 5 dernières minutes, pour éviter les oscillations (flapping). La montée, elle, est immédiate. Ces comportements se règlent dans le bloc `behavior` du HPA.

## Nettoyer

```bash
k delete ns tp3               # metrics-server est conservé pour le TP 4
k config set-context --current --namespace=default
exit
docker stop kind-box
```
