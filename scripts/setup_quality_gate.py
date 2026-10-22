"""Crée (ou met à jour) le Quality Gate du projet et l'associe au projet SonarQube.

Les conditions portent sur l'ensemble du code, pas seulement sur le nouveau code :
une baisse de couverture ou l'apparition d'un bug fait échouer le gate quelle que soit
la taille de la modification. Nécessite un token ayant le droit "Administer Quality Gates".

Usage : SONAR_TOKEN=... python scripts/setup_quality_gate.py
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

GATE_NAME = "Real-Time Sales"
PROJECT_KEY = "real-time-sales-devops"

# (métriques acceptées, opérateur, seuil d'erreur) : selon le mode de SonarQube
# (Standard ou MQR), bugs et vulnérabilités sont exposés sous l'un ou l'autre nom.
CONDITIONS = [
    (["coverage"], "LT", "80"),
    (["bugs", "software_quality_reliability_issues"], "GT", "0"),
    (["vulnerabilities", "software_quality_security_issues"], "GT", "0"),
    (["duplicated_lines_density"], "GT", "3"),
]


def api(host, token, method, path, params=None):
    data = urllib.parse.urlencode(params or {})
    url = f"{host}{path}"
    if method == "GET" and data:
        url, data = f"{url}?{data}", ""
    request = urllib.request.Request(url, data=data.encode() or None, method=method)
    auth = base64.b64encode(f"{token}:".encode()).decode()
    request.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else {}


def get_or_create_gate(host, token):
    try:
        return api(host, token, "GET", "/api/qualitygates/show", {"name": GATE_NAME})
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    api(host, token, "POST", "/api/qualitygates/create", {"name": GATE_NAME})
    return api(host, token, "GET", "/api/qualitygates/show", {"name": GATE_NAME})


def add_condition(host, token, metrics, op, error):
    for metric in metrics:
        try:
            api(host, token, "POST", "/api/qualitygates/create_condition",
                {"gateName": GATE_NAME, "metric": metric, "op": op, "error": error})
            return metric
        except urllib.error.HTTPError as http_error:
            if http_error.code != 400:
                raise
    sys.exit(f"Aucune des métriques {metrics} n'est acceptée par ce SonarQube")


def main():
    host = os.getenv("SONAR_HOST_URL", "http://localhost:9000")
    token = os.environ["SONAR_TOKEN"]

    gate = get_or_create_gate(host, token)
    for condition in gate.get("conditions", []):
        api(host, token, "POST", "/api/qualitygates/delete_condition", {"id": condition["id"]})

    print(f"Quality Gate « {GATE_NAME} » :")
    for metrics, op, error in CONDITIONS:
        metric = add_condition(host, token, metrics, op, error)
        print(f"  {metric:<35} {'<' if op == 'LT' else '>'} {error} => échec")

    projects = api(host, token, "GET", "/api/projects/search", {"projects": PROJECT_KEY})
    if not projects["components"]:
        api(host, token, "POST", "/api/projects/create",
            {"project": PROJECT_KEY, "name": "Real-Time Sales DevOps TP"})
    api(host, token, "POST", "/api/qualitygates/select",
        {"gateName": GATE_NAME, "projectKey": PROJECT_KEY})
    print(f"Associé au projet {PROJECT_KEY}")


if __name__ == "__main__":
    main()
