# TP 2 — Configuration et isolation

Une même image doit pouvoir tourner dans plusieurs environnements. Ce TP sort la configuration et les secrets des images, et isole les déploiements dans des namespaces.

## Les fichiers

- [`namespaces.yaml`](./namespaces.yaml) crée les namespaces `dev` et `test`.
- [`whoami.yaml`](./whoami.yaml) crée la ConfigMap `api-config`, le Deployment `api` (2 réplicas de `traefik/whoami`) et le Service `api`. La ConfigMap est injectée en variables d'environnement.
- [`whoami-test.yaml`](./whoami-test.yaml) contient la même application pour le namespace `test`, avec `WHOAMI_NAME=api-test` et 1 réplica (défi 1).
- [`index.html`](./index.html) est la page servie par nginx via une ConfigMap.
- [`site.yaml`](./site.yaml) crée le Deployment `site` (nginx), qui monte la ConfigMap `site` comme volume dans `/usr/share/nginx/html`.
- [`redis.yaml`](./redis.yaml) crée le Deployment et le Service `redis`, protégés par un mot de passe lu dans le Secret `redis-auth`.
- [`secret-file.yaml`](./secret-file.yaml) crée le Pod `secret-reader`, qui monte le Secret `redis-auth` en fichier, en lecture seule avec les permissions `0400` (défi 2).

Aucun manifeste ne précise de `namespace:`. Les ressources sont créées dans le namespace courant ou dans celui passé avec `-n`.

## Prérequis

Il faut un cluster accessible avec `kubectl`. Dans ce TP, `k` est un alias de `kubectl`, et les commandes se lancent dans le conteneur `kind-box` :

```bash
docker start kind-box
docker inspect -f '{{.State.Health.Status}}' kind-box   # attendre « healthy »
docker exec -it -w /work/tp-k8s/tp2 kind-box bash
```

## 1. Namespaces

Un namespace est un espace de nommage logique. Deux ressources peuvent porter le même nom dans deux namespaces différents. C'est aussi l'unité à laquelle on attache les droits (RBAC) et les quotas. Les namespaces ne s'imbriquent pas.

```bash
k apply -f namespaces.yaml
k config set-context --current --namespace=dev
k config view --minify | grep namespace
```

Certaines ressources appartiennent au cluster entier et pas à un namespace : `Node`, `Namespace`, `PersistentVolume`, `ClusterRole`… On les liste avec `k api-resources --namespaced=false`. Le namespace `kube-system` contient les composants internes du cluster : API server, etcd, scheduler, CoreDNS…

## 2. ConfigMaps

Une ConfigMap stocke de la configuration non sensible sous forme de paires clé/valeur, en dehors de l'image.

### En variables d'environnement

```bash
k apply -f whoami.yaml
k run tmp --rm -it --image=busybox:1.36 --restart=Never -- wget -qO- http://api
```

La ligne `Name:` de la réponse affiche la valeur de `WHOAMI_NAME`. `envFrom` injecte toutes les clés de la ConfigMap.

Les variables d'environnement sont lues une seule fois, au démarrage du conteneur. Après une modification de la ConfigMap, les Pods existants gardent l'ancienne valeur. `k apply` ne les recrée pas, car le template du Deployment n'a pas changé. Il faut forcer un redémarrage progressif :

```bash
k rollout restart deploy api
```

L'image `traefik/whoami` est construite `FROM scratch` et ne contient pas de shell, donc `k exec … -- env` échoue. Pour lire l'environnement, on peut attacher un conteneur de debug à un Pod :

```bash
POD=$(k get pod -l app=api -o name | head -1)
k debug -it $POD --image=busybox:1.36 --target=whoami -- sh -c 'tr "\0" "\n" < /proc/1/environ'
```

### Montée en fichiers

```bash
k create configmap site --from-file=index.html
k apply -f site.yaml
k port-forward --address 0.0.0.0 deploy/site 8080:80
curl http://localhost:8080
```

Chaque clé de la ConfigMap devient un fichier. Après un `k edit configmap site`, le fichier est mis à jour à chaud, sans redémarrage, au bout d'une minute environ. Le délai vient du kubelet, qui resynchronise les volumes périodiquement. La mise à jour est atomique : le kubelet écrit un nouveau dossier horodaté, puis il fait basculer le lien `..data`, vers lequel `index.html` pointe.

Deux limites :
- l'application doit relire le fichier (nginx le fait à chaque requête) ;
- un montage avec `subPath` n'est jamais mis à jour.

## 3. Secrets

Un Secret fonctionne comme une ConfigMap, mais il est destiné aux données sensibles.

```bash
k create secret generic redis-auth --from-literal=password='S3cr3t-M1ag3'
k get secret redis-auth -o jsonpath='{.data.password}' | base64 -d; echo
k apply -f redis.yaml
```

Les valeurs sont **encodées en base64, pas chiffrées**. Toute personne qui peut lire les Secrets du namespace obtient les mots de passe. La protection repose sur le RBAC. On ne versionne jamais un Secret dans Git : on utilise Sealed Secrets, SOPS ou un coffre externe. C'est pour ça que le Secret est créé en ligne de commande et qu'il n'existe pas de fichier YAML pour lui.

Dans `redis.yaml`, `secretKeyRef` injecte la clé `password` dans la variable `REDIS_PASSWORD`. La syntaxe `$(REDIS_PASSWORD)` la réutilise dans les arguments du conteneur.

```bash
k run cli --rm -it --image=redis:7-alpine --restart=Never -- redis-cli -h redis ping
# (error) NOAUTH Authentication required.
k run cli --rm -it --image=redis:7-alpine --restart=Never -- redis-cli -h redis -a 'S3cr3t-M1ag3' ping
# PONG
k exec deploy/redis -- env | grep REDIS_PASSWORD
```

Le mot de passe est visible en clair dans le conteneur. C'est le fonctionnement attendu : quiconque peut faire un `exec` dans un Pod voit ses secrets.

## 4. DNS entre namespaces

Chaque Service reçoit le nom `<service>.<namespace>.svc.cluster.local`, résolu par CoreDNS. Le fichier `/etc/resolv.conf` d'un Pod contient une ligne `search` qui commence par `<son-namespace>.svc.cluster.local`, et l'option `ndots:5`. C'est pour ça que le nom court `api` ne fonctionne que dans le même namespace.

| Nom utilisé                   | Depuis `dev` | Depuis `test` |
|-------------------------------|:------------:|:-------------:|
| `redis`                       | ✅           | ❌            |
| `redis.dev`                   | ✅           | ✅            |
| `redis.dev.svc.cluster.local` | ✅           | ✅            |

```bash
k run dns -n test --rm -it --image=busybox:1.36 --restart=Never -- sh
  wget -qO- http://api.dev
  nslookup api.dev.svc.cluster.local
  cat /etc/resolv.conf
```

Le `nslookup` de busybox n'applique les domaines de recherche qu'aux noms sans point. `nslookup redis.dev` y échoue donc, alors que `wget` et `ping` résolvent bien `redis.dev`.

Par défaut, les namespaces **n'isolent pas le réseau** : un Pod de `test` peut joindre les Services de `dev`. Pour bloquer ce trafic, il faut des NetworkPolicies.

## Défis

### Défi 1 — Même application dans `test`

```bash
k apply -f whoami-test.yaml -n test
k run tmp -n test --rm -it --image=busybox:1.36 --restart=Never -- wget -qO- http://api
k get pods -A -l app=api
```

Le `-n test` est indispensable. Le contexte courant est `dev` et les noms sont identiques : sans lui, on écraserait les ressources de `dev`.

Seules deux lignes diffèrent entre `whoami.yaml` et `whoami-test.yaml` (`WHOAMI_NAME` et `replicas`). Tout le reste est dupliqué. Avec plusieurs environnements et applications, cette duplication mène à des dérives et des erreurs de copier-coller. Kustomize et Helm (TP 4) résolvent ce problème avec une base commune et des différences par environnement.

### Défi 2 — Secret monté en fichier

```bash
k apply -f secret-file.yaml
k exec secret-reader -- ls -laL /etc/redis-auth/      # -r-------- password
k exec secret-reader -- cat /etc/redis-auth/password
k exec secret-reader -- mount | grep redis-auth       # tmpfs, ro
k exec secret-reader -- env | grep -i redis           # pas de mot de passe
```

Le fichier porte le nom de la clé du Secret. Il est stocké en mémoire (`tmpfs`), et non sur le disque du nœud. Un fichier est préférable à une variable d'environnement pour trois raisons :
- il n'est pas hérité par les processus enfants ;
- il n'apparaît pas dans les logs ou les crash dumps qui affichent l'environnement ;
- il est protégé par ses permissions, et il peut être mis à jour à chaud.

Il ne protège pas pour autant contre un utilisateur qui a le droit de faire `exec`.

## Nettoyer

```bash
k delete ns dev test          # supprime tout le contenu des namespaces
k config set-context --current --namespace=default
exit
docker stop kind-box
```
