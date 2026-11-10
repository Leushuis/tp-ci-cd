# TP Docker — optimisation

Application Node.js de départ. Chaque correction est notée ci-dessous avec la taille de l'image et les performances.

## Lancer

Depuis ce dossier :

```bash
docker build -t tp-docker-optimisation .
docker run --rm -p 3000:3000 tp-docker-optimisation
```

L'application répond sur [http://localhost:3000](http://localhost:3000). `Ctrl+C` arrête le conteneur.

## Mesurer

Taille :

```bash
docker images tp-docker-optimisation
```

Temps de build (`real`) :

```bash
/usr/bin/time -p docker build --no-cache -t tp-docker-optimisation .
```

Temps de réponse, conteneur démarré :

```bash
curl -o /dev/null -s -w "GET / : %{time_total}s\n" http://127.0.0.1:3000/
curl -o /dev/null -s -w "GET /big : %{time_total}s\n" http://127.0.0.1:3000/big
```
Médiane de 5 requêtes.

## Corrections

| Étape | Modification | Taille | Build | GET / | GET /big | Commentaire |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | Image de départ | 1.88 GB | 8.4 s | 2.4 ms | 2.0 ms | `maybe-big-file.txt` est absent. |
| 1 | Reformatage de `server.js` et `package.json` | 1.88 GB | 9.0 s | 2.0 ms | 2.1 ms | Indentation seulement. Taille inchangée. |
| 2 | Ajout de `maybe-big-file.txt` (2 MB) | 1.89 GB | 8.9 s | 1.7 ms | 5.7 ms | `/big` lit et renvoie le fichier. `GET /` ne change pas. |
