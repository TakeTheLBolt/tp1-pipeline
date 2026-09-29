"""Attend la fin de l'analyse SonarQube puis échoue si le Quality Gate n'est pas OK."""
import base64
import json
import os
import sys
import time
import urllib.request

REPORT_TASK = ".scannerwork/report-task.txt"
TIMEOUT = 300


def api_get(host, token, path):
    request = urllib.request.Request(f"{host}{path}")
    auth = base64.b64encode(f"{token}:".encode()).decode()
    request.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def read_report_task():
    with open(REPORT_TASK, encoding="utf-8") as report:
        return dict(line.strip().split("=", 1) for line in report if "=" in line)


def wait_for_analysis(host, token, task_id):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        task = api_get(host, token, f"/api/ce/task?id={task_id}")["task"]
        if task["status"] == "SUCCESS":
            return task["analysisId"]
        if task["status"] in ("FAILED", "CANCELED"):
            sys.exit(f"Analyse SonarQube en échec : {task['status']}")
        time.sleep(3)
    sys.exit(f"Timeout : analyse SonarQube non terminée après {TIMEOUT}s")


def main():
    token = os.environ["SONAR_TOKEN"]
    task = read_report_task()
    host = task["serverUrl"]

    analysis_id = wait_for_analysis(host, token, task["ceTaskId"])
    gate = api_get(host, token, f"/api/qualitygates/project_status?analysisId={analysis_id}")
    status = gate["projectStatus"]

    print(f"Quality Gate : {status['status']}")
    for condition in status["conditions"]:
        print(
            f"  {condition['metricKey']:<35} {condition['status']:<6} "
            f"valeur={condition.get('actualValue')} seuil={condition.get('errorThreshold')}"
        )

    if status["status"] != "OK":
        sys.exit("Quality Gate en échec : pipeline arrêtée")


if __name__ == "__main__":
    main()
