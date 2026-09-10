# 1. Architektur und Infrastruktur

## 1.1 Architektur

Die vollständige Architektur ist in `01_Architekturdiagramm.drawio` dargestellt.

Die Daten werden aus Shopify und der Meta Marketing API über dlt nach BigQuery geladen. Die Transformation erfolgt anschließend mit dbt. Dabei werden die Rohdaten zunächst in Staging-Modelle überführt und danach in wiederverwendbare Zwischenmodelle sowie das Marketing-Mart überführt. Das zentrale Ergebnis ist `fct_marketing_performance`, das für Reporting und nachgelagerte Automatisierungen genutzt wird.

Die Orchestrierung läuft mit Prefect auf einer Hetzner Cloud VM. Prefect Server, Worker und PostgreSQL werden über Docker Compose betrieben. Der Worker führt die dlt-, dbt- und Python-Tasks aus, während Speicherung und SQL-Verarbeitung in BigQuery stattfinden.

Dadurch bleibt die selbst gehostete Infrastruktur klein. Rechenintensive Datenverarbeitung wird nicht auf dem Hetzner-Server ausgeführt.

Eine spätere LLM-Analyse kann auf den bereits validierten Marketing-Daten aufbauen und vor dem Slack Alert zusätzliche Erklärungen erzeugen. Die Berechnung der Kennzahlen selbst bleibt deterministisch in SQL beziehungsweise Python.


## 1.2 Tech Stack

| Bereich            | Technologie            | Begründung                                                         |
| ------------------ | ---------------------- | ------------------------------------------------------------------ |
| Ingestion          | dlt                    | Python-nativ, geeignet für API-Ingestion und inkrementelles Laden  |
| Data Warehouse     | BigQuery               | Serverless, nutzungsbasierte Kosten, kein eigener Datenbankbetrieb |
| Transformation     | dbt Core, BigQuery SQL | SQL-Modellierung, Abhängigkeiten und Data Tests                    |
| Orchestrierung     | Prefect OSS            | Scheduling, Retries, Abhängigkeiten und Run States                 |
| Application Logic  | Python                 | Ingestion-Logik und Automatisierungen                              |
| Runtime            | Docker Compose         | Reproduzierbare Deployment-Umgebung                                |
| Infrastruktur      | Hetzner Cloud          | Niedrige Fixkosten für den Orchestrierungs-Workload                |
| Prefect Metadata   | PostgreSQL             | Persistenz für Prefect State und Metadaten                         |
| Python Environment | uv                     | Dependency Locking und reproduzierbare Umgebungen                  |
| Versionierung      | GitHub                 | Versionierung von Code und Konfiguration                           |

Damit bleibt das Data Warehouse vollständig verwaltet, während die vergleichsweise kleine Orchestrierungsumgebung selbst gehostet wird.

## 1.3 Managed Services und Self-hosted

BigQuery nutze ich als Managed Service. Ein selbst betriebenes Data Warehouse würde Backup, Skalierung, Wartung und Verfügbarkeit zusätzlich in das Team verlagern, ohne für den aktuellen Workload einen entsprechenden Vorteil zu bieten.

Prefect betreibe ich zunächst selbst auf Hetzner. Bei wenigen Pipelines sind die direkten Kosten gering und die Umgebung bleibt vollständig kontrollierbar. Dafür müssen Betriebssystem, Docker, Prefect, PostgreSQL, Backups und Security Updates selbst betreut werden.

Ich würde diese Entscheidung neu bewerten, sobald die operative Komplexität deutlich steigt. Ein sinnvoller Prüfpunkt wären etwa drei bis fünf Data Engineers, mehrere Dutzend produktive Workflows oder mehrere gleichzeitig benötigte Worker. Für BigQuery wäre weniger die Anzahl der Bestellungen entscheidend als dauerhaft hohe Scan-Volumina und deutlich steigende monatliche Query-Kosten.

Ein fünffaches Bestellvolumen allein wäre für mich noch kein Grund für einen Plattformwechsel.

## 1.4 Bottlenecks bei fünffachem Bestellvolumen

BigQuery wäre bei diesem Wachstum voraussichtlich nicht der erste Engpass.

Die ersten Risiken liegen eher in folgenden Bereichen:

* API Rate Limits und Pagination bei Shopify und Meta
* unnötige Full Loads statt inkrementeller Extraktion
* vollständige Scans historischer Daten in dbt
* wiederholte Berechnung der gesamten Customer-Historie
* CPU- und Memory-Konkurrenz auf einem einzelnen Prefect Worker

Ich würde deshalb früh auf inkrementelles Laden, Partitionierung nach Datum, inkrementelle dbt-Modelle und einen begrenzten Lookback für nachträglich geänderte Daten setzen.

`first_order_date` sollte bei wachsendem Datenbestand ebenfalls inkrementell gepflegt werden, statt täglich die gesamte Bestellhistorie neu zu berechnen.

Falls ein Worker nicht mehr ausreicht, können zunächst weitere Worker ergänzt oder Concurrency Limits angepasst werden. Ein Wechsel der gesamten Orchestrierungsplattform wäre dafür nicht erforderlich.

## 1.5 Infrastrukturkosten

Für das initiale Setup reicht ein kleiner Hetzner Cloud Server.

| Komponente     | Monatliche Schätzung |
| -------------- | -------------------: |
| Hetzner CX33   |        ca. 10,10 EUR |
| Primary IPv4   |         ca. 0,60 EUR |
| Hetzner Backup |         ca. 2,02 EUR |
| BigQuery       |      ca. 0 bis 5 EUR |
| OSS-Lizenzen   |                0 EUR |
| Gesamt         |    ca. 15 bis 20 EUR |

Als Budget würde ich mit etwas Reserve etwa 15 bis 25 EUR pro Monat ansetzen.

BigQuery bietet aktuell für On-demand Queries ein monatliches Freikontingent von 1 TiB verarbeiteter Daten sowie 10 GiB Storage. Für diesen kleinen täglichen Batch-Workload sollte der Warehouse-Anteil deshalb zunächst gering bleiben.

Der aktuelle CX33-Preis in Deutschland beträgt 10,10 EUR pro Monat inklusive 19 Prozent MwSt. und exklusive IPv4. Eine Primary IPv4 kostet 0,60 EUR pro Monat. Hetzner Backups kosten 20 Prozent des Serverpreises.

Personalkosten und bereits vorhandene SaaS-Abonnements sind nicht enthalten.

## 1.6 Reliability und Security

* Secrets werden nicht in Git gespeichert.
* BigQuery Service Accounts erhalten nur die erforderlichen Berechtigungen.
* Prefect UI und PostgreSQL werden nicht ungeschützt öffentlich erreichbar gemacht.
* Temporäre API- und Netzwerkfehler erhalten begrenzte Retries.
* Fehlgeschlagene dbt Tests stoppen nachgelagerte Business Alerts.
* Prefect Flow States und Logs dienen dem Monitoring.
* Hetzner und PostgreSQL werden regelmäßig gesichert.

Die Ausführungsreihenfolge bleibt eindeutig.

```text
Ingestion
    |
    v
Transformation
    |
    v
Data Tests
    |
    v
Business Consumption
```

Nur erfolgreich transformierte und validierte Daten werden für Reporting und Automatisierungen verwendet.
