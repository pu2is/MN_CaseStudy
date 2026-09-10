# 3. Automatisierung und KI

## 3.1 ROAS-Warnung

Der Prefect Flow führt zuerst `dbt build` aus und prüft danach den gewünschten Berichtstag in `fct_marketing_performance`.

```text
dbt build
-> ROAS abfragen
-> Ergebnis klassifizieren
-> bei ROAS < 1,5 Slack-Warnung
```

Der Standardwert für den Schwellenwert ist 1,5. Ohne explizites Datum prüft der Flow den Vortag in `REPORTING_TIMEZONE`. Der Berichtstag wird einmal zu Beginn des Flows fixiert. Für manuelle Backfills kann ein Datum explizit übergeben werden.

Die BigQuery-Abfrage hat drei Retries mit 10, 30 und 60 Sekunden Abstand. `dbt build` und Slack-Zustellung werden nicht automatisch wiederholt.

Bei `DATA_UNAVAILABLE` schlägt der Flow fehl und sendet eine Betriebswarnung. Bei `NO_SPEND` wird keine Performance-Warnung gesendet. Fehlende Meta-Daten werden als `DATA_UNAVAILABLE` klassifiziert. `NO_SPEND` gilt nur für einen vorhandenen Tagesdatensatz mit explizitem `ad_spend = 0`. Zusätzlich wird ein Berichtstag als `DATA_UNAVAILABLE` behandelt, wenn während der Transformation ungültige Shopify- oder Meta-Datensätze aus den Kennzahlen ausgeschlossen wurden. Bestätigte Slack-Zustellungen werden über einen lokalen SQLite-Status dedupliziert, damit ein erneuter Lauf denselben Alert nicht doppelt versendet.

Der tägliche Prefect-Zeitplan läuft um 08:00 Uhr in `REPORTING_TIMEZONE` mit maximal einem parallelen lokalen Lauf. Die Ingestion muss vorher abgeschlossen sein.

## 3.2 KI-Ausblick

Das LLM erklärt bereits berechnete und validierte Kennzahlen. Es berechnet CAC und ROAS nicht selbst.

```text
ROAS < 1,5
-> deterministische Analysedaten
-> LLM
-> Ausgabevalidierung
-> Slack
```

Für die Analyse können je Kampagne Spend, Impressions, Clicks, CTR, CPC und CPM sowie Veränderungen gegenüber historischen Vergleichszeiträumen vorbereitet werden. Auf Shopify-Ebene eignen sich Revenue, Orders, Average Order Value und New Customers.

Das aktuelle Mock-Schema kann nicht belegen, welche Kampagne einen Umsatzrückgang verursacht hat. Dafür fehlen attribuierte Conversions, attribuierter Revenue und ein definiertes Attribution Window.

Das LLM erhält nur aggregierte strukturierte Daten und keinen freien SQL-, API- oder Schreibzugriff. Externe Textfelder werden als nicht vertrauenswürdige Daten behandelt. Die Ausgabe sollte eine feste Struktur mit `summary`, `hypotheses`, `evidence_ids`, `limitations` und `suggested_checks` verwenden.

Vor dem Versand werden Schema, Evidence IDs und referenzierte Zahlen geprüft. Bei Timeout oder ungültiger Antwort wird die numerische Basiswarnung ohne LLM-Erklärung gesendet. Das Modell darf weder Kennzahlen ändern noch einen bereits ausgelösten Alert unterdrücken.
