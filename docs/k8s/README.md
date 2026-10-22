# Déploiement Kubernetes local : observations

## Déploiement

```bash
kubectl create secret generic postgres-secret \
  --from-literal=POSTGRES_USER=sales --from-literal=POSTGRES_PASSWORD=<mot-de-passe>
kubectl apply -f k8s/
```

Sorties enregistrées juste après le déploiement :

- [get-pods.txt](get-pods.txt) : `kubectl get pods -o wide`
- [get-deployments.txt](get-deployments.txt) : `kubectl get deployments`
- [get-services.txt](get-services.txt) : `kubectl get services`

Les 5 Deployments (`kafka`, `postgres`, `sales-api`, `spark-streaming`, `zookeeper`) sont disponibles
(1/1) et le Job `kafka-create-topic` est terminé (`Completed`), sans aucun redémarrage de Pod. Tous les
Services sont de type `ClusterIP` : ils ne sont joignables qu'à l'intérieur du cluster.

## Vérifications

| Composant | Vérification | Résultat |
|---|---|---|
| PostgreSQL | `kubectl exec deploy/postgres -- psql -U sales -d sales -c "\dt"` | table `processed_orders` créée par `init.sql` |
| Kafka | `kubectl exec deploy/kafka -- kafka-topics --bootstrap-server kafka:29092 --list` | topic `sales.orders` présent |
| Spark | `kubectl logs deploy/spark-streaming` | `Streaming query made progress`, puis en attente de données |

## Démarrage : erreurs transitoires observées

Tous les composants démarrent en même temps : Kubernetes n'a pas d'équivalent au `depends_on` de
docker-compose.

- **Job `kafka-create-topic`** : `Connection to node -1 (kafka/10.99.237.121:29092) could not be
  established` pendant une trentaine de secondes, le temps que le broker démarre. Le client réessaie
  puis affiche `Created topic sales.orders.` L'adresse est celle du Service `kafka` : la résolution DNS
  par le nom du Service fonctionne.
- **Spark** : `Timed out waiting for a node assignment`, puis `UnknownTopicOrPartitionException` (Kafka
  pas encore prêt, puis topic pas encore créé). Le lecteur Kafka de Spark réessaie et le streaming démarre
  dès que le topic existe, sans redémarrage du Pod. Si le job s'arrêtait, le Deployment le relancerait.

## A. Accès à l'API (port-forward)

Sortie : [test-api.txt](test-api.txt). Avec `kubectl port-forward service/sales-api 8000:8000`, l'API
répond depuis le poste : `/api/health` renvoie `{"status":"UP","service":"sales-api"}`, `/api/products`
la liste des 4 produits et `/docs` un code HTTP 200.

## B. Mise à l'échelle

Sortie : [scale.txt](scale.txt). Après `kubectl scale deployment/sales-api --replicas=3`, deux nouveaux Pods
sont créés en quelques secondes à côté du Pod existant (`3/3` disponibles), chacun avec sa propre adresse
IP. Le Service `sales-api` a alors trois endpoints et répartit les requêtes entre eux. Au retour à
`--replicas=1`, le ReplicaSet supprime deux Pods.

## C. Suppression d'un Pod

Sortie : [delete-pod.txt](delete-pod.txt).

Après `kubectl delete pod sales-api-7767ff7f79-nk79m`, le ReplicaSet du Deployment a constaté qu'il ne
restait plus aucun Pod sur l'unique réplica demandé. Il a aussitôt créé un Pod de remplacement,
`sales-api-7767ff7f79-429tw`, avant même la fin de l'arrêt de l'ancien. Le nouveau Pod a un autre nom et
une autre adresse IP, et il était prêt en 6 secondes (sonde `/api/health`). Le Service, qui sélectionne les
Pods par le label `app: sales-api`, l'a pris en charge sans aucune modification : l'état souhaité (1
réplica) a été rétabli automatiquement.

Limite observée : `kubectl port-forward service/...` se rattache au Pod choisi à son lancement. La
suppression de ce Pod coupe le port-forward, qu'il faut relancer. Dans le cluster, le Service bascule
automatiquement vers le nouveau Pod ; avec un seul réplica, l'API reste toutefois indisponible les quelques
secondes nécessaires à son démarrage (avec plusieurs réplicas, les autres Pods continueraient à répondre).

## D. Flux Data

Sortie : [test-flux-data.txt](test-flux-data.txt). La commande `C100 / P001 / 3 × 100` envoyée à l'API
(`POST /api/orders`, réponse `total_amount: 300.0`, `order_id: ORD-7563C678F8`) est publiée dans Kafka,
consommée par Spark puis enregistrée dans PostgreSQL environ 1,6 s plus tard, avec
`total_amount = 300.00`. Tous les échanges passent par les Services Kubernetes (`kafka:29092`,
`postgres:5432`).
