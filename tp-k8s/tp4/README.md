# TP 4 — Multi-environnements avec Kustomize

Au TP 2, déployer la même application dans deux namespaces avait obligé à dupliquer tout le YAML pour changer deux lignes. Kustomize résout ce problème sans templates : une **base** commune, et un **overlay** par environnement qui ne décrit que les différences.

## Arborescence

```
tp4/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   └── service.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   └── namespace.yaml
    └── prod/
        ├── kustomization.yaml
        ├── patch-resources.yaml
        ├── hpa.yaml
        └── secret.env          (non versionné)
```

- [`base/`](./base) décrit l'application `api` (`traefik/whoami`) sans rien de spécifique à un environnement : ni namespace, ni selector, ni labels.
- [`overlays/dev/`](./overlays/dev) déploie la base dans le namespace `dev`, avec le préfixe `dev-` et `WHOAMI_NAME=api-dev`.
- [`overlays/prod/`](./overlays/prod) déploie la base dans le namespace `prod`, avec 3 réplicas, l'image `v1.10.2`, des ressources dimensionnées, une liveness probe, un Secret, un HPA et l'option `--verbose`.

## Prérequis

Kustomize est intégré à kubectl :

```bash
k kustomize <dossier>     # affiche le YAML rendu, sans rien envoyer au cluster
k apply -k <dossier>      # applique le rendu
```

Le fichier `overlays/prod/secret.env` doit être créé localement. Il est exclu de Git par la règle `*.env` du `.gitignore` à la racine du repo :

```
API_TOKEN=prod-t0k3n-a-ne-pas-commiter
```

## 1. La base

```bash
k kustomize base
```

Dans le rendu :
- **Labels.** `labels` avec `includeSelectors: true` ajoute `app.kubernetes.io/name: api` aux métadonnées, au `selector` du Service, au `selector` du Deployment et au template des Pods. Les selectors et les labels sont donc toujours cohérents.
- **ConfigMap.** `configMapGenerator` génère une ConfigMap nommée `api-config-<hash>`, où le hash est calculé sur son contenu.
- **Référence.** Le `envFrom` du Deployment est réécrit avec ce nom hashé.

Modifier une valeur change le hash, donc le nom de la ConfigMap, donc le template du Pod. Un rolling update est alors déclenché automatiquement. Au TP 2, il fallait un `k rollout restart`.

## 2. Overlay dev

```bash
k kustomize overlays/dev
k apply -k overlays/dev
k get all,cm -n dev
k port-forward --address 0.0.0.0 -n dev svc/dev-api 8080:80
curl http://localhost:8080          # Name: api-dev
```

| Transformer | Effet |
|---|---|
| `namespace: dev` | Toutes les ressources vont dans `dev`, sans dépendre du contexte ni de `-n` |
| `namePrefix: dev-` | `api` devient `dev-api`, et les références (`envFrom`…) suivent. Le Namespace n'est pas préfixé |
| `labels: env: dev` | Label ajouté aux métadonnées, mais pas aux selectors (pas d'`includeSelectors`) |
| `configMapGenerator` + `behavior: merge` | Fusionne les valeurs avec la ConfigMap de la base. Le nom doit être `api-config`, sans préfixe |

Le label `env` est volontairement exclu des selectors : le selector d'un Deployment est immuable, on n'y met que des labels stables.

## 3. Overlay prod

```bash
k create ns prod
k kustomize overlays/prod
k apply -k overlays/prod
k get deploy,hpa,cm,secret -n prod
```

| Besoin | Outil Kustomize |
|---|---|
| 3 réplicas | `replicas` |
| Image `v1.10.2` | `images` (`newTag`) |
| Ressources, liveness, Secret dans l'environnement | patch strategic merge [`patch-resources.yaml`](./overlays/prod/patch-resources.yaml) |
| Option `--verbose` | patch JSON 6902 (`op: add` sur `/spec/template/spec/containers/0/args`) |
| Secret `API_TOKEN` | `secretGenerator` (lit `secret.env`, nom hashé) |
| Autoscaling 3 → 8 Pods à 70 % CPU | [`hpa.yaml`](./overlays/prod/hpa.yaml) |

Points vérifiés dans le rendu :
- **Le HPA vise `prod-api`.** Le fichier contient `scaleTargetRef.name: api`, et Kustomize le préfixe parce qu'il sait que ce champ référence un Deployment.
- **`envFrom` pointe vers les deux noms hashés** (`prod-api-config-…` et `prod-api-secret-…`). `envFrom` est une liste sans clé de fusion : le strategic merge la **remplace entièrement**. C'est pour ça que le patch répète la `configMapRef`.
- **La `readinessProbe` de la base est conservée.** Le strategic merge fusionne les champs du conteneur, qu'il retrouve par son nom (`whoami`).
- **Les patches utilisent le nom de la base** (`api`), pas le nom préfixé.
- **Labels du Secret et du HPA.** Ces ressources sont créées dans l'overlay. Elles portent `env: prod` mais pas le label de la base, parce que chaque `kustomization.yaml` ne transforme que ses propres ressources.

| | Strategic merge | JSON 6902 |
|---|---|---|
| Forme | Extrait de YAML fusionné avec la ressource | Liste d'opérations `add` / `replace` / `remove` |
| Usage | Ajouter ou modifier plusieurs champs, lisible | Opération précise, suppression d'un champ |
| Piège | Les listes sans clé sont remplacées | Les index (`containers/0`) dépendent de l'ordre |

## 4. Workflow et vérifications

Avant d'appliquer une modification (ici `WHOAMI_NAME=api-prod-v2`), on vérifie son effet :

```bash
k diff -k overlays/prod                                      # différence avec le cluster réel
k kustomize overlays/prod | k apply --dry-run=server -f -    # validation par l'API server
k apply -k overlays/prod
k rollout status deploy/prod-api -n prod
k get cm -n prod
```

Le `k diff` montre une nouvelle ConfigMap et une seule ligne modifiée dans le Deployment (la référence `configMapRef`). Le Secret, le Service et le HPA sont `unchanged`. Le rolling update a lieu sans `rollout restart`.

L'ancienne ConfigMap reste dans le cluster. Un `k rollout undo deploy/prod-api -n prod` revient donc à l'ancienne version **avec** son ancienne configuration. Les ConfigMaps obsolètes se nettoient avec `k apply --prune`, ou avec un outil GitOps (Argo CD, Flux) qui fait suivre au cluster l'état du dépôt Git.

## Nettoyer

```bash
k delete -k overlays/dev
k delete -k overlays/prod
k delete ns prod
```
