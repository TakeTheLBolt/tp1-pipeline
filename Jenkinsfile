pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        // Le Spark de la stack est arrêté pendant les tests : un seul build à la fois.
        disableConcurrentBuilds()
    }

    environment {
        VENV = '.venv'
        CI_TAG = "ci-${env.BUILD_NUMBER}"
        // Conteneurs de test propres au build : les tests s'exécutent contre le code du commit.
        SPARK_IT = "sales-spark-it-${env.BUILD_NUMBER}"
        SPARK_E2E = "sales-spark-e2e-${env.BUILD_NUMBER}"
        API_E2E = "sales-api-e2e-${env.BUILD_NUMBER}"
        // Jenkins est sur le réseau Docker "data-platform" : on cible les services par leur nom.
        KAFKA_BOOTSTRAP_SERVERS_TEST = 'kafka:29092'
        POSTGRES_HOST_TEST = 'postgres'
        POSTGRES_PORT_TEST = '5432'
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Environment') {
            steps {
                sh 'python3 --version'
                sh 'docker --version'
            }
        }

        stage('Install') {
            steps {
                sh '''
                    python3 -m venv $VENV
                    $VENV/bin/pip install --quiet -r requirements.txt
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    $VENV/bin/python -m pytest tests/unit \
                      --cov=app \
                      --cov-report=xml:coverage.xml \
                      --cov-report=term-missing \
                      --junitxml=test-results-unit.xml
                '''
            }
        }

        stage('Integration Tests') {
            // Code du workspace : API lancée avec uvicorn, Spark avec le script du commit.
            steps {
                sh '''
                    sh scripts/ci_env.sh isolate
                    sh scripts/ci_env.sh spark-workspace $SPARK_IT

                    KAFKA_BOOTSTRAP_SERVERS=kafka:29092 KAFKA_TOPIC=sales.orders \
                      $VENV/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 > sales-api-it.log 2>&1 &
                    API_PID=$!
                    trap "kill $API_PID || true" EXIT

                    sh scripts/ci_env.sh wait-ready http://127.0.0.1:8001/api/health $SPARK_IT

                    API_URL=http://127.0.0.1:8001 RUN_INTEGRATION_TESTS=true \
                      $VENV/bin/python -m pytest tests/integration -v \
                      --junitxml=test-results-integration.xml
                '''
            }
        }

        stage('Build') {
            steps {
                sh '''
                    docker build -f docker/api/Dockerfile -t sales-api:$CI_TAG .
                    docker build -f docker/spark/Dockerfile -t sales-spark-streaming:$CI_TAG .
                '''
            }
        }

        stage('E2E Tests') {
            // Images construites par le stage Build.
            steps {
                sh '''
                    sh scripts/ci_env.sh stop $SPARK_IT
                    sh scripts/ci_env.sh api-image $API_E2E sales-api:$CI_TAG
                    sh scripts/ci_env.sh spark-image $SPARK_E2E sales-spark-streaming:$CI_TAG
                    sh scripts/ci_env.sh wait-ready http://$API_E2E:8000/api/health $SPARK_E2E

                    API_URL=http://$API_E2E:8000 RUN_E2E_TESTS=true \
                      $VENV/bin/python -m pytest tests/e2e -v \
                      --junitxml=test-results-e2e.xml
                '''
            }
        }

        stage('SonarQube') {
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh '''
                        sonar-scanner \
                          -Dsonar.host.url=http://sonarqube:9000 \
                          -Dsonar.token=$SONAR_TOKEN
                    '''
                }
            }
        }

        stage('Quality Gate') {
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh '$VENV/bin/python scripts/wait_quality_gate.py'
                }
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'test-results-*.xml'
            sh '''
                sh scripts/ci_env.sh cleanup $SPARK_IT $SPARK_E2E $API_E2E || true
                docker rmi sales-api:$CI_TAG sales-spark-streaming:$CI_TAG || true
            '''
            archiveArtifacts allowEmptyArchive: true, artifacts: 'coverage.xml, sales-*.log'
        }
        success {
            echo 'Pipeline OK'
        }
        failure {
            echo 'Pipeline FAILED : voir l\'étape en erreur'
        }
    }
}
