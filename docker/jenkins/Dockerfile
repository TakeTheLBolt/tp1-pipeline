FROM jenkins/jenkins:lts-jdk17

USER root

RUN apt-get update \
    && apt-get install -y docker.io python3 python3-pip python3-venv git curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN python3 --version && docker --version

ARG SONAR_SCANNER_VERSION=6.2.1.4610
RUN curl -fsSL -o /tmp/scanner.zip       https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux-x64.zip     && unzip -q /tmp/scanner.zip -d /opt     && mv /opt/sonar-scanner-${SONAR_SCANNER_VERSION}-linux-x64 /opt/sonar-scanner     && ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner     && rm /tmp/scanner.zip     && sonar-scanner --version

USER jenkins

RUN jenkins-plugin-cli --plugins \
    workflow-aggregator \
    git \
    junit \
    pipeline-stage-view \
    sonar
