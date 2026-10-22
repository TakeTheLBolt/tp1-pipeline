#!/bin/sh
# Environnement de test CI : exécute le code du commit contre Kafka et PostgreSQL de la stack
# docker compose, sur le topic sales.orders. Le Spark de la stack est arrêté pendant les tests
# pour que seul le Spark du commit écrive dans processed_orders.
set -euf

STACK_SPARK=sales-spark-streaming
SPARK_BASE_IMAGE=apache/spark:3.5.7
SPARK_SUBMIT="/opt/spark/bin/spark-submit --master local[2] --conf spark.jars.ivy=/opt/ivy \
--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.7"
SPARK_ENV="-e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 -e KAFKA_TOPIC=sales.orders \
-e POSTGRES_HOST=postgres -e POSTGRES_DB=sales -e POSTGRES_USER=sales -e POSTGRES_PASSWORD=sales"

network() {
    docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' sales-kafka
}

# Vérifie que Kafka et PostgreSQL sont prêts, puis arrête le Spark de la stack.
isolate() {
    for svc in sales-kafka sales-postgres; do
        status=$(docker inspect -f '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo absent)
        if [ "$status" != healthy ]; then
            echo "$svc indisponible ($status) : lancer docker compose up -d"
            exit 1
        fi
    done
    docker stop "$STACK_SPARK" >/dev/null 2>&1 || true
}

# Spark avec le script du workspace (avant Build) : image de base + dépendance du Dockerfile Spark.
spark_workspace() {
    docker create --name "$1" --network "$(network)" -u root $SPARK_ENV \
        -v sales-spark-ivy-cache:/opt/ivy "$SPARK_BASE_IMAGE" \
        sh -c "pip install --quiet psycopg2-binary==2.9.9 && $SPARK_SUBMIT /tmp/sales_stream.py"
    docker cp spark/sales_stream.py "$1:/tmp/sales_stream.py"
    docker start "$1"
}

# Spark à partir de l'image construite par le stage Build.
spark_image() {
    docker run -d --name "$1" --network "$(network)" $SPARK_ENV \
        -v sales-spark-ivy-cache:/opt/ivy "$2" $SPARK_SUBMIT /opt/spark-app/sales_stream.py
}

# API à partir de l'image construite par le stage Build.
api_image() {
    docker run -d --name "$1" --network "$(network)" \
        -e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 -e KAFKA_TOPIC=sales.orders "$2"
}

# Attend que l'URL réponde et que l'UI Spark du conteneur soit active (polling avec timeout).
wait_ready() {
    url=$1
    spark=$2
    for i in $(seq 1 60); do
        if [ "$(docker inspect -f '{{.State.Running}}' "$spark")" != true ]; then
            echo "$spark s'est arrêté"
            docker logs --tail 80 "$spark"
            exit 1
        fi
        if curl -sf "$url" >/dev/null && curl -sf "http://$spark:4040/api/v1/applications" >/dev/null; then
            echo "Environnement de test prêt"
            return 0
        fi
        echo "Environnement de test en démarrage ($i/60)"
        sleep 5
    done
    echo "Timeout : environnement de test indisponible"
    exit 1
}

# Sauvegarde les logs puis supprime les conteneurs de test.
stop() {
    for c in "$@"; do
        if docker inspect "$c" >/dev/null 2>&1; then
            docker logs "$c" >"$c.log" 2>&1 || true
            docker rm -f "$c" >/dev/null 2>&1 || true
        fi
    done
}

# Supprime les conteneurs de test et redémarre le Spark de la stack.
cleanup() {
    stop "$@"
    docker start "$STACK_SPARK" >/dev/null 2>&1 || true
}

command=$1
shift
case "$command" in
    isolate) isolate ;;
    spark-workspace) spark_workspace "$@" ;;
    spark-image) spark_image "$@" ;;
    api-image) api_image "$@" ;;
    wait-ready) wait_ready "$@" ;;
    stop) stop "$@" ;;
    cleanup) cleanup "$@" ;;
    *) echo "Commande inconnue : $command" && exit 1 ;;
esac
