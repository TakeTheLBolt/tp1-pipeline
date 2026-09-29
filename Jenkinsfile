pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        VENV = '.venv'
        // Jenkins est sur le réseau Docker "data-platform" : on cible les services par leur nom.
        API_URL = 'http://sales-api:8000'
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

        stage('Wait for Infrastructure') {
            steps {
                sh '''
                    for i in $(seq 1 30); do
                        curl -sf $API_URL/api/health && exit 0
                        echo "API not ready, retry $i/30"
                        sleep 5
                    done
                    echo "API unreachable" && exit 1
                '''
            }
        }

        stage('Integration Tests') {
            steps {
                sh '''
                    RUN_INTEGRATION_TESTS=true $VENV/bin/python -m pytest tests/integration -v \
                      --junitxml=test-results-integration.xml
                '''
            }
        }

        stage('Build') {
            steps {
                sh '''
                    docker build -f docker/api/Dockerfile -t sales-api:ci-$BUILD_NUMBER .
                    docker build -f docker/spark/Dockerfile -t sales-spark-streaming:ci-$BUILD_NUMBER .
                '''
            }
        }

        stage('E2E Tests') {
            steps {
                sh '''
                    RUN_E2E_TESTS=true $VENV/bin/python -m pytest tests/e2e -v \
                      --junitxml=test-results-e2e.xml
                '''
            }
        }

        stage('SonarQube') {
            steps {
                echo 'TODO: configure SonarQube Scanner / server credentials.'
            }
        }

        stage('Quality Gate') {
            steps {
                echo 'TODO: waitForQualityGate() after SonarQube integration.'
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'test-results-*.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'coverage.xml'
        }
        success {
            echo 'Pipeline OK'
        }
        failure {
            echo 'Pipeline FAILED : voir l\'étape en erreur'
        }
    }
}
