# TP Docker

Application Flask minimale. La route `/` répond `Hello, World!` sur le port 8080.

## Fichiers

- `app.py` : application Flask
- `requirements.txt` : dépendance Flask
- `Dockerfile` : construction de l'image

## Construire l'image

Depuis ce dossier :

```bash
docker build -t tp-docker .
```

## Lancer le conteneur

```bash
docker run --rm -p 8080:8080 tp-docker
```

L'application est accessible sur [http://localhost:8080](http://localhost:8080).

Pour l'arrêter, utilisez `Ctrl+C` dans le terminal où le conteneur tourne.
