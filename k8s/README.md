# Déploiement Kubernetes local (Minikube)

## Images du projet

Les images de l'API et de Spark sont construites à partir des Dockerfiles du dépôt, directement dans
Minikube (le cluster ne voit pas les images du Docker local) :

```bash
minikube image build -t sales-api:tp3 -f docker/api/Dockerfile .
minikube image build -t sales-spark:tp3 -f docker/spark/Dockerfile .
minikube image ls | grep tp3
```

Les manifestes utilisent ces noms avec `imagePullPolicy: IfNotPresent`.

## Correspondance avec docker-compose.yml

| Service Compose | Image | Port | Paramètres repris |
|---|---|---|---|
| `sales-api` | `sales-api:tp3` (`docker/api/Dockerfile`) | 8000 | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TOPIC` |
| `postgres` | `postgres:16-alpine` | 5432 | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `infra/postgres/init.sql`, volume de données |
| `zookeeper` | `confluentinc/cp-zookeeper:7.6.14` | 2181 | `ZOOKEEPER_CLIENT_PORT`, `ZOOKEEPER_TICK_TIME` |
| `kafka` | `confluentinc/cp-kafka:7.6.14` | 29092 | listeners, `KAFKA_ZOOKEEPER_CONNECT`, réplication à 1 |
| `kafka-init` | `confluentinc/cp-kafka:7.6.14` | - | création du topic `sales.orders` |
| `spark-streaming` | `sales-spark:tp3` (`docker/spark/Dockerfile`) | - | variables Kafka et PostgreSQL, `spark-submit` avec le connecteur Kafka |

Jenkins, SonarQube et le cluster Spark standalone (`spark-master`, `spark-worker`) ne sont pas déployés :
Jenkins et SonarQube sont hors périmètre, et le job Spark tourne en mode `local` dans son Pod.

## Secret PostgreSQL (hors dépôt)

Les identifiants de la base ne sont ni dans une ConfigMap ni dans Git. Ils sont fournis par un Secret
créé en ligne de commande avant le déploiement :

```bash
kubectl create secret generic postgres-secret \
  --from-literal=POSTGRES_USER=sales \
  --from-literal=POSTGRES_PASSWORD=<mot-de-passe>
```

PostgreSQL et Spark lisent `POSTGRES_USER` et `POSTGRES_PASSWORD` depuis ce Secret.

## Manifestes

| Fichier | Ressources |
|---|---|
| `configmap.yaml` | ConfigMap `sales-config` : hôtes Kafka et PostgreSQL (noms des Services), topic, base |
| `postgres-init-configmap.yaml` | ConfigMap `postgres-init` : copie de `infra/postgres/init.sql` |
| `postgres-pvc.yaml` | PersistentVolumeClaim `postgres-data` (1 Gi) |
| `postgres-deployment.yaml`, `postgres-service.yaml` | Deployment et Service `postgres` (5432) |
| `zookeeper.yaml` | Deployment et Service `zookeeper` (2181) |
| `kafka.yaml` | Deployment et Service `kafka` (29092) |
| `kafka-topic-job.yaml` | Job `kafka-create-topic` : création du topic `sales.orders` |
| `api-deployment.yaml`, `api-service.yaml` | Deployment et Service `sales-api` (8000) |
| `spark-deployment.yaml` | Deployment `spark-streaming` : job Spark en mode `local[2]` |

Tous les Pods ont `enableServiceLinks: false` : sinon Kubernetes injecte des variables comme
`KAFKA_PORT=tcp://...` (déduites du nom des Services), que les images Confluent interprètent comme de la
configuration, et Kafka refuse de démarrer.

## Déploiement

```bash
kubectl apply -f k8s/
kubectl get deployments
kubectl get pods -o wide
kubectl get services
kubectl port-forward service/sales-api 8000:8000
```
