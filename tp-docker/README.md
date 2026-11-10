# TP Docker

Application Flask reliée à MongoDB. La route `/` incrémente un compteur de visites dans la base `tp-docker` et répond sur le port 8080.

## Fichiers

- `app.py` : application Flask, connexion MongoDB via Flask-PyMongo
- `requirements.txt` : dépendances Python
- `Dockerfile` : image de l'application
- `docker-compose.yml` : conteneurs `app` et `mongo`

## Lancer les conteneurs

Depuis ce dossier :

```bash
docker compose up --build
```

L'application est accessible sur [http://localhost:8080](http://localhost:8080). MongoDB est exposé sur le port 27017.

L'application attend que MongoDB réponde avant de démarrer. La variable `MONGO_URI` vaut `mongodb://mongo:27017/tp-docker` : `mongo` est le nom du service dans Compose.

Pour arrêter les conteneurs, utilisez `Ctrl+C`, puis :

```bash
docker compose down
```
