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
