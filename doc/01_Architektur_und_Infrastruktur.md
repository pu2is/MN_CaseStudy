# 1. Architektur und Infrastruktur

## 1.1 Architektur

Die vollständige Architektur ist in [`01_Architekturdiagramm.drawio`](01_Architekturdiagramm.drawio) dargestellt.

Shopify- und Meta-Daten werden mit dlt nach BigQuery geladen. dbt übernimmt die Transformation von Raw Data über Staging- und Intermediate-Modelle bis zum Marketing-Mart. Das finale Modell `fct_marketing_performance` wird für Reporting und Automatisierungen verwendet.

In der Zielarchitektur laufen Prefect Server, Worker und PostgreSQL per Docker Compose auf einer Hetzner Cloud VM. Der Worker kann dlt-, dbt- und Python-Tasks ausführen. In diesem Repository sind dbt sowie die ROAS-Prüfung und Slack-Benachrichtigung implementiert; die Ingestion über dlt ist Teil der vorgeschlagenen Zielarchitektur. Speicherung und SQL-Verarbeitung liegen in BigQuery.

Eine spätere LLM-Analyse baut auf validierten Marketing-Daten auf. CAC und ROAS bleiben deterministisch berechnet.

## 1.2 Technologie-Stack

| Bereich | Technologie | Begründung |
| --- | --- | --- |
| Ingestion | dlt | Python-nativ, geeignet für API-Ingestion und inkrementelles Laden |
| Data Warehouse | BigQuery | Serverless, nutzungsbasierte Kosten, kein eigener Datenbankbetrieb |
| Transformation | dbt Core, BigQuery SQL | SQL-Modellierung, Abhängigkeiten und Data Tests |
| Orchestrierung | Prefect OSS | Scheduling, Retries, Abhängigkeiten und Run States |
| Anwendungslogik | Python | Ingestion-Logik und Automatisierungen |
| Laufzeit | Docker Compose | Reproduzierbare Deployment-Umgebung |
| Infrastruktur | Hetzner Cloud | Niedrige Fixkosten für den Orchestrierungs-Workload |
| Prefect-Metadaten | PostgreSQL | Persistenz für Prefect State und Metadaten |
| Python-Umgebung | uv | Dependency Locking und reproduzierbare Umgebungen |
| Versionierung | GitHub | Versionierung von Code und Konfiguration |

BigQuery bleibt vollständig verwaltet. Die kleinere Orchestrierungsumgebung wird selbst betrieben.

## 1.3 Managed Service und Self-hosted

BigQuery nutze ich als Managed Service. Ein selbst betriebenes Data Warehouse würde zusätzlichen Aufwand für Backup, Skalierung, Wartung und Verfügbarkeit erzeugen.

Prefect würde ich zunächst selbst auf Hetzner betreiben. Bei wenigen Pipelines bleiben die direkten Kosten niedrig. Dafür liegen Betriebssystem, Docker, Prefect, PostgreSQL, Backups und Security Updates beim Team.

Eine Neubewertung wäre sinnvoll bei etwa drei bis fünf Data Engineers, mehreren Dutzend produktiven Workflows, mehreren gleichzeitig benötigten Workern oder verbindlichen SLA-Anforderungen. Für BigQuery wären dauerhaft hohe Scan-Volumina und deutlich steigende Query-Kosten relevanter als die reine Bestellzahl.

Ein fünffaches Bestellvolumen allein erfordert keinen Plattformwechsel.

## 1.4 Engpässe bei fünffachem Bestellvolumen

BigQuery wäre bei diesem Wachstum voraussichtlich nicht der erste Engpass. Kritischer sind API Rate Limits und Pagination, Full Loads, vollständige historische Scans sowie die wiederholte Berechnung der Customer-Historie.

Dagegen helfen inkrementelles Laden, Partitionierung nach Datum, inkrementelle dbt-Modelle und ein begrenzter Lookback für nachträgliche Änderungen. `first_order_date` kann bei wachsendem Datenbestand ebenfalls inkrementell gepflegt werden.

Bei höherer Parallelität kann ein einzelner Prefect Worker zum Engpass werden. Dann lassen sich zunächst weitere Worker ergänzen oder Concurrency Limits anpassen.

## 1.5 Infrastrukturkosten

| Komponente | Monatliche Schätzung |
| --- | ---: |
| Hetzner CX33 | ca. 10,10 EUR |
| Primary IPv4 | ca. 0,60 EUR |
| Hetzner Backup | ca. 2,02 EUR |
| BigQuery | ca. 0 bis 5 EUR |
| OSS-Lizenzen | 0 EUR |
| Gesamt | ca. 15 bis 20 EUR |

Mit Reserve würde ich für das initiale Setup etwa 15 bis 25 EUR pro Monat einplanen. Personalkosten und bestehende SaaS-Abonnements sind nicht enthalten.

## 1.6 Zuverlässigkeit und Sicherheit

Secrets werden nicht in Git gespeichert. BigQuery Service Accounts erhalten nur die benötigten Berechtigungen. Prefect UI und PostgreSQL sollten nicht ungeschützt öffentlich erreichbar sein.

Im ausführbaren Flow wird `dbt build` nicht automatisch wiederholt. Die BigQuery-Abfrage des ROAS hat begrenzte Retries. Erst nach einem erfolgreichen Build wird der Zieltag geprüft. Nicht verfügbare oder ungültige Daten führen zu einer Betriebswarnung und einem fehlgeschlagenen Flow. Bestätigte Slack-Zustellungen werden lokal protokolliert, damit ein erneuter Lauf nicht denselben Alert erneut sendet.
