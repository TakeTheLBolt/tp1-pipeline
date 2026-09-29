FROM jenkins/jenkins:lts-jdk17

USER root

RUN apt-get update \
    && apt-get install -y docker.io python3 python3-pip python3-venv git curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3 --version && docker --version

USER jenkins

RUN jenkins-plugin-cli --plugins \
    workflow-aggregator \
    git \
    junit \
    pipeline-stage-view \
    sonar
