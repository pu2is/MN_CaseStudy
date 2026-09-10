# mellow NOIR Fallstudie

Dieses Repository enthält die Lösung der Fallstudie für die Position Full-Stack Data Engineer. Die Datenmodelle berechnen tägliche Blended-Proxys für CAC und ROAS aus Shopify- und Meta-Daten. Die optionale Automatisierung prüft den ROAS mit Prefect und sendet bei einem Wert unter dem Schwellenwert eine Slack-Warnung.

## Dokumentation

| Inhalt | Datei |
| --- | --- |
| Architektur, Tech Stack, Trade-offs, Skalierung und Kosten | [`doc/01_Architektur_und_Infrastruktur.md`](doc/01_Architektur_und_Infrastruktur.md) |
| Architekturdiagramm | [`doc/01_Architekturdiagramm.drawio`](doc/01_Architekturdiagramm.drawio) |
| Datenpipeline, Modellierung, Kennzahlen und Datenqualität | [`doc/02_Data_Pipelines_und_Modellierung.md`](doc/02_Data_Pipelines_und_Modellierung.md) |
| Automatisierung und KI-Ausblick | [`doc/03_Automatisierung_und_KI.md`](doc/03_Automatisierung_und_KI.md) |

## Erste Schritte

Voraussetzungen sind Python 3.11 oder neuer, `uv`, ein Google-Cloud-Projekt mit BigQuery und lokale Application Default Credentials.

```bash
uv sync
export DBT_PROFILES_DIR=.
gcloud auth application-default login
```

Für BigQuery werden mindestens diese Variablen benötigt.

```bash
export BIGQUERY_PROJECT="<gcp-project-id>"
export BIGQUERY_DATASET="mellow_noir"
export BIGQUERY_LOCATION="EU"
export REPORTING_TIMEZONE="Europe/Berlin"
```

Die Raw-Tabellen `src_shopify_orders` und `src_meta_insights` müssen im Dataset `BIGQUERY_DATASET` vorhanden sein. Die Ingestion selbst ist nicht Teil des ausführbaren Codes.

### dbt ausführen

```bash
uv run dbt build
```

Die Modelle werden in drei Schemas materialisiert.

```text
<dataset>_staging
<dataset>_intermediate
<dataset>_marts
```

Das finale Modell liegt unter `<dataset>_marts.fct_marketing_performance`.

### Tests ausführen

```bash
uv run pytest
```

Die Python-Tests mocken BigQuery und Slack. Die SQL-Modelltests verwenden lokale Fixtures mit DuckDB und SQLGlot. Ein echter BigQuery-Lauf wird dadurch nicht ersetzt.

### ROAS-Warnung einmalig ausführen

Für Performance-Warnungen wird `SLACK_WEBHOOK_URL` verwendet. `OPS_SLACK_WEBHOOK_URL` kann optional einen getrennten Kanal für technische Fehler definieren. Vor dem Flow-Start muss mindestens einer dieser Webhooks konfiguriert sein.

```bash
export SLACK_WEBHOOK_URL="<slack-webhook>"
export ROAS_ALERT_THRESHOLD="1.5"
uv run python -m orchestration.flow
```

Ein bestimmtes Datum kann manuell geprüft werden.

```bash
uv run python -m orchestration.flow --date 2026-09-09
```

### Täglichen Prefect Flow starten

```bash
uv run python -m orchestration.schedule
```

Der Flow läuft täglich um 08:00 Uhr in `REPORTING_TIMEZONE` und setzt voraus, dass die Raw-Daten vorher geladen wurden.

## Projektstruktur

```text
.
├── doc/                 Dokumentation und Architekturdiagramm
├── models/              dbt Modelle
├── macros/              benutzerdefinierte dbt Tests
├── orchestration/       Prefect Flow und Slack-Automatisierung
├── tests/               automatisierte Python- und Modelltests
├── dbt_project.yml      dbt Projektkonfiguration
├── profiles.yml         BigQuery Profil ohne Secrets
├── pyproject.toml       Python-Abhängigkeiten
└── uv.lock              gesperrte Abhängigkeitsversionen
```

Secrets werden ausschließlich zur Laufzeit über Umgebungsvariablen oder lokale Google-Credentials bereitgestellt.
