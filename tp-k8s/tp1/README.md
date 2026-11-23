# TP Kubernetes

Ce dossier contient des exemples de manifestes Kubernetes au format YAML. Un manifeste décrit une ressource et son état souhaité ; `kubectl` l'envoie au cluster, qui cherche ensuite à maintenir cet état.

## Les ressources

- [`pod.yaml`](./pod.yaml) crée un Pod nommé `hello` avec un conteneur Nginx. Un Pod est l'unité de base qui héberge un ou plusieurs conteneurs.
- [`deployment.yaml`](./deployment.yaml) crée un Deployment nommé `web`, qui maintient trois réplicas du conteneur `traefik/whoami:v1.10.2`. Le Deployment peut recréer les Pods si nécessaire.
- [`service.yaml`](./service.yaml) crée un Service nommé `web` qui expose le port 80 et cible les Pods portant l'étiquette `app: web`. Il fournit un point d'accès stable aux Pods sélectionnés.

Le Deployment ajoute l'étiquette `app: web` à ses Pods ; cette étiquette correspond au sélecteur du Service. Sans cette correspondance, le Service ne trouverait pas les Pods à qui transmettre le trafic.

## Prérequis

Il faut un cluster Kubernetes accessible ainsi que `kubectl` configuré pour ce cluster. Par défaut, les commandes ci-dessous utilisent l'espace de noms `default`.

## Appliquer et vérifier

Depuis ce dossier, appliquer les trois manifestes :

```bash
kubectl apply -f pod.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

Ou appliquer tout le dossier :

```bash
kubectl apply -f .
```

Vérifier les ressources et l'état des Pods :

```bash
kubectl get pods
kubectl get deployments
kubectl get services
kubectl get pods --show-labels
```

Pour obtenir davantage de détails sur une ressource :

```bash
kubectl describe pod hello
kubectl describe deployment web
kubectl describe service web
```

Les Pods du Deployment peuvent être listés avec leur étiquette :

```bash
kubectl get pods -l app=web
```

## Nettoyer

Supprimer les ressources créées à partir des manifestes :

```bash
kubectl delete -f .
```
