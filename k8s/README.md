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
