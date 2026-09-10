# 2. Datenpipelines und Modellierung

## 2.1 Modellfluss

Die Transformation beginnt bei den bereits geladenen BigQuery-Quelltabellen.

```text
src_shopify_orders
-> stg_shopify_orders
-> int_customer_first_order
-> int_shopify_daily
                           \
                            -> fct_marketing_performance
                           /
src_meta_insights
-> stg_meta_insights
-> int_meta_daily
```

Staging- und Intermediate-Modelle werden als Views materialisiert. `fct_marketing_performance` ist eine nach `date` partitionierte Tabelle und wird bei jedem `dbt build` neu aufgebaut.

## 2.2 Granularität und Kennzahlen

`fct_marketing_performance` enthält eine Zeile pro Kalendertag zwischen dem frühesten und spätesten beobachteten Quelldatum. Shopify und Meta werden vor dem Join getrennt auf Tagesebene aggregiert. Dadurch entsteht kein Fan-out zwischen Bestellungen und Kampagnen.

| Feld | Definition |
| --- | --- |
| `revenue` | Summe gültiger Shopify `total_price` am Berichtstag |
| `orders` | Anzahl identifizierbarer und datierbarer, nach `order_id` deduplizierter Orders |
| `new_customers` | Anzahl unterschiedlicher `customer_id`, deren erste beobachtete Order auf diesen Tag fällt |
| `ad_spend` | Summe gültiger Meta-Spend-Werte am Berichtstag |
| `impressions` | Summe gültiger Meta Impressions am Berichtstag |
| `clicks` | Summe gültiger Meta Clicks am Berichtstag |
| `invalid_shopify_revenue_rows` | Anzahl der Shopify Orders am Berichtstag mit ungültigem `total_price`, die nicht in Revenue eingehen |
| `invalid_meta_rows` | Anzahl der Meta Campaign Rows am Berichtstag mit ungültigen Spend-, Impression- oder Click-Werten, die aus der Aggregation ausgeschlossen werden |
| `roas` | `revenue / ad_spend` |
| `cac` | `ad_spend / new_customers` in EUR |

ROAS und CAC sind Blended-Proxys. Das Mock-Schema enthält keinen Attribution Key zwischen Shopify-Bestellungen und Meta-Kampagnen, keine Ausgaben anderer Kanäle und kein Attributionsfenster. Ein echter Meta-attribuierter ROAS, CAC oder Kampagnenumsatz ist damit nicht berechenbar. `discount_code` wird bereinigt und beibehalten, ist aber kein verlässlicher Attribution Key zu einer Meta-Kampagne.

## 2.3 Bereinigung und Deduplizierung

`stg_shopify_orders` entfernt Zeilen ohne verwendbare `order_id` oder `created_at`. Bei mehreren Versionen derselben `order_id` wird die Zeile mit dem neuesten `created_at` behalten. Da das Mock-Schema keinen Ingestion-Timestamp enthält, ist dies eine deterministische Näherung und keine verlässliche Latest-Record-Logik. Bei identischem `created_at` kann das Mock-Schema keinen eindeutigen Datensatz bestimmen.

Negative oder nicht interpretierbare `total_price`-Werte bleiben sichtbar und werden mit `total_price_is_invalid` markiert. Sie zählen weiterhin als Order, werden aber nicht in `revenue` aufgenommen. Der entsprechende dbt Test hat Severity `warn`.

`stg_meta_insights` entfernt Zeilen ohne verwendbares `date` oder `campaign_id`. Bei mehreren Zeilen für dieselbe Kombination aus `date` und `campaign_id` wird deterministisch nach Spend, Impressions und Clicks ausgewählt. Negative oder fehlende Spend-, Impression- oder Click-Werte setzen `has_invalid_negative_value`. Solche Zeilen werden vollständig aus `int_meta_daily` ausgeschlossen. Die Non-negative-Tests auf Staging-Ebene erzeugen Warnungen und blockieren den Build nicht.

## 2.4 Annahmen

- Die Shopify-Store-Währung ist EUR und entspricht der Währung des Meta Spend.
- `total_price` ist die verfügbare Revenue-Definition. Rückerstattungen, Stornierungen, Steuern, Versand und Testbestellungen können mit dem Mock-Schema nicht getrennt behandelt werden.
- Shopify `created_at` wird als UTC-Zeitpunkt interpretiert. `order_date` wird mit `REPORTING_TIMEZONE` berechnet, standardmäßig `Europe/Berlin`.
- Der Meta-Account-Kalender muss dieselbe Reporting-Zeitzone verwenden.
- Für die Ermittlung von New Customers wird eine vollständige Customer-Order-Historie vorausgesetzt.
- Bestellungen ohne `customer_id` zählen zu Revenue und Orders, aber nicht zu New Customers.

## 2.5 Fehlende Daten und Nullteiler

Das finale Modell erzeugt innerhalb des beobachteten Datumsbereichs eine Date Spine. Fehlt an einem Tag eine Quelle, bleiben deren Kennzahlen `NULL`. Fehlende Rows bedeuten nicht automatisch null Bestellungen oder null Werbeausgaben, sie können auch auf eine unvollständige Ingestion hinweisen. Im Produktivbetrieb sollte deshalb ein separater Load-Completion-Status die Vollständigkeit je Quelle und Berichtstag bestätigen.

`SAFE_DIVIDE` verhindert Fehler bei Nullteilern. Bei Spend 0 oder unbekannt ist ROAS `NULL`. Bei 0 New Customers ist CAC `NULL`. Bei Spend 0 und positiven New Customers ergibt CAC 0.

Die Automatisierung unterscheidet zusätzlich zwischen Datenverfügbarkeit und Performance. Ein fehlender oder ungültiger Revenue-Wert führt zu `DATA_UNAVAILABLE`. Ein fehlender `ad_spend` wird als `DATA_UNAVAILABLE` behandelt, da ohne separaten Load-Completion-Status nicht zwischen fehlgeschlagener Ingestion und einem fachlich gültigen Tag ohne Meta-Daten unterschieden werden kann. Ein expliziter `ad_spend` von 0 wird dagegen als `NO_SPEND` behandelt und erzeugt keine Low-ROAS-Warnung.
Die wichtigsten Grenzfälle sind:

| Situation | ROAS | CAC | Verhalten |
| --- | ---: | ---: | --- |
| Revenue 120, Spend 100, 2 New Customers | 1.2 | 50 EUR | Low-ROAS-Warnung |
| ROAS genau 1.5 | 1.5 | abhängig von New Customers | keine Low-ROAS-Warnung |
| Meta-Daten fehlen, `ad_spend` ist `NULL` | `NULL` | abhängig von verfügbaren Daten | `DATA_UNAVAILABLE` |
| Spend ist explizit 0, New Customers vorhanden | `NULL` | 0 | `NO_SPEND` |
| Spend > 0, New Customers 0 | abhängig von Revenue | `NULL` | ROAS wird normal bewertet |
| Revenue 0, Spend > 0 | 0 | abhängig von New Customers | Low-ROAS-Warnung |
| Revenue fehlt oder ist ungültig | `NULL` | abhängig von verfügbaren Daten | `DATA_UNAVAILABLE` |
| Invalid Meta rows vorhanden (`invalid_meta_rows > 0`) | abhängig von verfügbaren Daten | abhängig von verfügbaren Daten | `DATA_UNAVAILABLE` |
| Invalid Shopify revenue rows vorhanden (`invalid_shopify_revenue_rows > 0`) | abhängig von verfügbaren Daten | abhängig von verfügbaren Daten | `DATA_UNAVAILABLE` |


## 2.6 Datenqualität

Die dbt Tests prüfen unter anderem Unique Keys, Not-null-Anforderungen, nicht negative Kennzahlen und `new_customers <= orders`.

Quellnahe Anomalien wie negative oder nicht interpretierbare Werte werden auf Staging-Ebene markiert und aus den fachlichen Aggregationen ausgeschlossen. Die Anzahl ausgeschlossener Datensätze wird jedoch bis in `fct_marketing_performance` weitergegeben. Enthält der Berichtstag solche Anomalien, wird das Ergebnis von der Automatisierung als `DATA_UNAVAILABLE` behandelt, damit keine potenziell unvollständige Kennzahl als valide Performance veröffentlicht wird. Verletzungen der finalen Modellintegrität bleiben Fehler und blockieren die nachgelagerte Automatisierung.

Die lokalen Modelltests verwenden DuckDB und SQLGlot mit Fixtures. Sie prüfen die Geschäftslogik ohne BigQuery-Credentials, ersetzen aber keinen nativen BigQuery `dbt build`.
