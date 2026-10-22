# Rapport Industrialisation de la pipeline Real-Time Sales

Projet : Real-Time Sales Analytics Pipeline (FastAPI, Kafka, PySpark, PostgreSQL)
Outils CI : Jenkins, SonarQube, pytest 

dépôt : https://github.com/TakeTheLBolt/tp1-pipeline

## 1. Architecture du projet

```text
Sales API (FastAPI) ──► Kafka (sales.orders) ──► PySpark Streaming ──► PostgreSQL (processed_orders)

GitHub ──► Jenkins ──► tests unitaires / intégration / build / E2E ──► SonarQube ──► Quality Gate
```

L'API valide une commande, calcule `total_amount = quantity × unit_price` et publie l'événement dans Kafka.
Spark lit le topic et écrit dans `processed_orders`. Jenkins et SonarQube sont dans le même
`docker-compose.yml`, sur le réseau Docker `data-platform`.

## 2. Stratégie de tests

Trois niveaux, du plus rapide au plus proche de la production :

| Niveau | Dossier | Services réels | Rôle |
|---|---|---|---|
| Unitaire | `tests/unit/` | non (Kafka mocké) | règles métier, validation, événement |
| Intégration | `tests/integration/` | oui (Docker) | deux liaisons : API→Kafka et Kafka→Spark→PostgreSQL |
| End-to-End | `tests/e2e/` | oui (Docker) | parcours complet API → PostgreSQL |

Les tests d'intégration et E2E sont activés par les variables `RUN_INTEGRATION_TESTS` et `RUN_E2E_TESTS`,
pour qu'un `pytest` lancé sans Docker n'échoue pas. Les attentes utilisent un **polling avec timeout**
(`tests/integration/helpers.py`, fonction `wait_until`), jamais un `sleep` fixe.

## 3. Tests unitaires

10 tests dans `tests/unit/test_orders.py`, couverture de `app/` : **100 %** (41 lignes).

- calcul du montant total (dont l'arrondi flottant : 3 × 0,1 = 0,3) ;
- quantité valide, nulle, négative, supérieure à 1000, non entière ;
- prix nul, négatif, trop élevé, non numérique ;
- identifiants client et produit trop courts ;
- format (`ORD-` + 10 caractères hexadécimaux) et unicité de l'identifiant de commande ;
- structure de l'événement (champs, valeurs, horodatage UTC, sérialisation JSON) ;
- configuration du producteur Kafka et endpoints (`/api/health`, `/api/products`, `POST /api/orders` avec
  Kafka mocké : 201, 404 produit inconnu, 422 charge invalide).

## 4. Tests d'intégration

- **Test A : API → Kafka** (`test_api_kafka.py`) : un `POST /api/orders` est envoyé, puis un consumer
  (groupe unique) relit `sales.orders` jusqu'à retrouver l'`order_id`, et les valeurs sont contrôlées.
- **Test B : Kafka → Spark → PostgreSQL** (`test_spark_postgres.py`) : un événement est publié directement
  dans Kafka, puis on attend (timeout 90 s) qu'il apparaisse dans `processed_orders` avec les bonnes valeurs.

## 5. Scénario End-to-End

`tests/e2e/test_sales_pipeline.py`, en Given / When / Then :

- **Given** l'infrastructure est démarrée (`/api/health` répond `UP`) ;
- **When** la commande `C100 / P001 / quantité 3 / prix 100` est envoyée à l'API ;
- **Then** la ligne apparaît dans PostgreSQL (attente avec timeout) avec `total_amount = 300`.

Un second test vérifie qu'une commande invalide (quantité négative) est rejetée avec un 422.

## 6. Pipeline Jenkins

`Jenkinsfile`, stages dans l'ordre du sujet : Checkout → Environment → Install (venv) → Unit Tests →
Integration Tests → Build (`docker build` des images API et Spark, taguées `ci-<n° de build>`) → E2E Tests →
SonarQube → Quality Gate.

**Tester le code du commit, pas celui déjà déployé.** Les tests d'intégration et E2E ne visent pas les
conteneurs de la stack `docker compose` (qui exécutent le code du dernier `docker compose up --build`), mais
le code du commit, lancé par `scripts/ci_env.sh` contre Kafka et PostgreSQL de la stack, sur le topic
`sales.orders` :

- *Integration Tests* (avant le Build) : l'API du workspace est lancée avec `uvicorn` dans l'agent Jenkins, et
  Spark tourne dans un conteneur éphémère `sales-spark-it-<n>` (image `apache/spark` + script
  `spark/sales_stream.py` du commit).
- *E2E Tests* (après le Build) : l'API et Spark tournent à partir des images qui viennent d'être construites
  (`sales-api-e2e-<n>`, `sales-spark-e2e-<n>`). C'est donc l'artefact livrable qui est validé de bout en bout.

Pendant ces deux stages, le Spark de la stack est arrêté : seul le Spark du commit consomme `sales.orders`,
donc une ligne trouvée dans `processed_orders` prouve que c'est bien le code du commit qui l'a traitée
(Spark tourne en mode `local[2]`, le cluster standalone étant occupé par le job de la stack). Le script
attend que l'API réponde et que Spark soit démarré (polling avec timeout, arrêt immédiat si le conteneur
Spark s'arrête). En fin de build (`post { always }`), les logs des conteneurs de test sont archivés, les
conteneurs et les images sont supprimés et le Spark de la stack est redémarré (il reprend à son offset,
l'insertion idempotente évite les doublons). `disableConcurrentBuilds()` empêche deux builds de se gêner.

Vérification : avec un filtre Spark volontairement cassé (toutes les commandes rejetées), le test
*Kafka → Spark → PostgreSQL* échoue au timeout et la pipeline s'arrête au stage *Integration Tests* ; avant
cette correction, le Spark de la stack aurait écrit la ligne et le test serait passé.

La pipeline s'arrête au premier stage en échec. Les résultats JUnit sont publiés et `coverage.xml` est
archivé. Jenkins est sur le réseau Docker : les tests ciblent les services par leur nom
(`kafka:29092`, `postgres`, `sales-api-e2e-<n>`).

![Stage View Jenkins](images/jenkins-stage-view.png)

## 7. Configuration SonarQube

- Projet `real-time-sales-devops` (`sonar-project.properties`) : sources `app`, tests `tests`, rapport de
  couverture `coverage.xml`.
- `sonar-scanner` est installé dans l'image Jenkins. Le token est stocké dans les credentials Jenkins
  (`sonar-token`, type Secret text) et n'apparaît pas dans le dépôt.
- Le scanner cible `http://sonarqube:9000` depuis Jenkins.

## 8. Quality Gate

**Gate personnalisé « Real-Time Sales », sur l'ensemble du code.** Le gate par défaut (*Sonar way*) ne
contrôle que le *nouveau code*, et SonarQube y ignore la couverture quand le nouveau code compte trop peu de
lignes : du code non testé pouvait donc passer (voir §10). Le gate du projet porte sur le code complet :

| Condition | Échec si |
|---|---|
| Coverage | < 80 % |
| Bugs | > 0 |
| Vulnerabilities | > 0 |
| Duplications | > 3 % |

Il est défini dans le dépôt (`scripts/setup_quality_gate.py`, ou `make quality-gate`) plutôt que cliqué dans
l'interface : le script crée le gate, remet ses conditions à jour, crée le projet s'il n'existe pas et lui
associe le gate. Il est idempotent et permet de reconstruire la configuration après un `docker compose down -v`.

Le stage Quality Gate exécute `scripts/wait_quality_gate.py` : il attend la fin de l'analyse via l'API
SonarQube, lit le statut du Quality Gate, affiche chaque condition et **fait échouer la pipeline** si le
statut n'est pas `OK`. Sortie sur le code du dépôt :

```text
Quality Gate : OK
  coverage                            OK     valeur=100.0 seuil=80
  duplicated_lines_density            OK     valeur=0.0 seuil=3
  bugs                                OK     valeur=0 seuil=0
  vulnerabilities                     OK     valeur=0 seuil=0
```

## 9. Résultats obtenus

Analyse SonarQube (code complet) :

| | Première analyse | Après corrections |
|---|---|---|
| Bugs (Reliability) | 0 | 0 |
| Vulnérabilités (Security) | 0 | 0 |
| Code smells (Maintainability) | 2 | **0** |
| Couverture | 100 % | 100 % |
| Duplications | 0 % | 0 % |
| Quality Gate | Passed | Passed |

Tests : 10 unitaires, 3 d'intégration (dont le `test_health` du projet de départ), 2 E2E  tous verts.

![Issues avant correction](images/sonar-issues-avant.png)
![Vue d'ensemble après correction](images/sonar-overall-apres.png)
![Issues après correction](images/sonar-issues-apres.png)

**Détection d'une régression fonctionnelle (build n°7).** Le calcul du montant a été volontairement cassé
(`quantity + unit_price`). Jenkins a échoué au stage *Unit Tests* (4 tests en échec, par exemple
`assert 52.0 == 100.0`) et tous les stages suivants ont été sautés. Le calcul correct a ensuite été rétabli
et la pipeline est repassée au vert.

**Détection d'une dégradation de la qualité.** Une fonction de calcul de remise (16 lignes) a été
ajoutée à `app/main.py` sans test. Les 10 tests unitaires restent verts, mais la couverture tombe à 73,7 % et
le Quality Gate échoue, ce qui arrête la pipeline :

```text
Quality Gate : ERROR
  coverage                            ERROR  valeur=73.7 seuil=80
  duplicated_lines_density            OK     valeur=0.0 seuil=3
  bugs                                OK     valeur=0 seuil=0
  vulnerabilities                     OK     valeur=0 seuil=0
Quality Gate en échec : pipeline arrêtée
```

Avec l'ancien gate (*Sonar way*, nouveau code uniquement), une modification de ce type était passée. Le code
de démonstration a ensuite été retiré et le gate est repassé à `OK`.

## 10. Problèmes rencontrés

- **Aucun plugin Jenkins installé** : `Pipeline`, `Git`, `JUnit` et `Sonar` ajoutés à l'image Jenkins.
- **Option `timestamps()` refusée** : le plugin Timestamper n'était pas installé, l'option a été retirée.
- **`python3 -m venv` et `docker compose` absents** du conteneur Jenkins : ajout de `python3-venv` et
  utilisation de `docker build` à la place de `docker compose build`.
- **`localhost` inaccessible depuis Jenkins** : les tests utilisent les noms de services Docker.
- **`kafka-python` 2.0.2 incompatible avec Python 3.13** (`kafka.vendor.six.moves`) : passage à 2.0.6.
- **Spark plantait au démarrage** (`UnknownTopicOrPartitionException`) car le topic n'existait pas encore :
  ajout d'un service `kafka-init` qui crée `sales.orders`, et `restart: on-failure`.
- **Spark plantait après un redémarrage** (clé primaire dupliquée, checkpoint perdu) : écriture rendue
  idempotente (`ON CONFLICT DO NOTHING`).
- **`docker compose down -v`** supprime aussi les volumes : SonarQube, Jenkins et PostgreSQL sont réinitialisés.
- **Les tests d'intégration et E2E visaient la stack déjà lancée** : une modification de `app/` ou de
  `spark/` n'était pas testée tant que la stack n'était pas reconstruite à la main. Corrigé par
  `scripts/ci_env.sh` (API et Spark du commit, Spark de la stack arrêté pendant les tests).
- **Quality Gate non déclenché par du code non testé** : le gate par défaut ne contrôle que le nouveau code
  et ignore la couverture sous un certain nombre de nouvelles lignes. Corrigé par un gate personnalisé portant
  sur l'ensemble du code (§8).

## 11. Corrections réalisées

- SonarQube, `app/main.py` : le code 404 de `POST /api/orders` est documenté dans `responses`.
- SonarQube, `tests/unit/test_orders.py` : `pytest.raises(Exception)` remplacé par `pytest.raises(ValidationError)`.
- Infrastructure : service `kafka-init`, redémarrage automatique de Spark, écriture idempotente dans PostgreSQL.
- CI : image Jenkins complétée, Jenkinsfile industrialisé, contrôle du Quality Gate scripté.
- CI : les tests d'intégration exécutent l'API et Spark du workspace, les tests E2E les images construites ;
  `test_api.py` appelle désormais l'API réelle au lieu d'un `TestClient` en mémoire.
- Qualité : Quality Gate personnalisé sur l'ensemble du code (couverture, bugs, vulnérabilités,
  duplications), versionné dans `scripts/setup_quality_gate.py`.
- Des commits de démonstration (« TEST REGRESSION ») figurent dans l'historique ; le code non testé qu'ils
  avaient ajouté a été supprimé par le commit « Nettoyage ».

## Question de synthèse

Comment garantir automatiquement qu'une modification ne dégrade ni le fonctionnement ni la qualité ?
Chaque `push` peut déclencher Jenkins, qui enchaîne des contrôles de plus en plus larges : tests unitaires
(règles métier, en quelques secondes), tests d'intégration (les composants réels communiquent), build des
images, test E2E sur ces images (le parcours complet), tous exécutés contre le code du commit, puis SonarQube et le Quality Gate (bugs, vulnérabilités,
duplications, couverture). Un échec à n'importe quel stage arrête la pipeline, comme l'a montré le build
n°7. Le dépôt garde l'historique, et la Pull Request permet de relire avant intégration.
