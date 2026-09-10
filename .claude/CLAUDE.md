# mellow NOIR — Case Study Conventions

This file governs how work in this repo should be approached. It applies to all code,
commits, issues, and documentation produced here.

## 1. Implementation Strategy

The implementation follows one continuous path from infrastructure design to business value:

```
Project Foundation
        |
        v
Architecture and Infrastructure
        |
        v
Source Data
        |
        v
Staging Models
        |
        v
Business Logic and Aggregation
        |
        v
fct_marketing_performance
        |
        v
Data Quality Validation
        |
        +----------------------+
        |                      |
        v                      v
Daily Reporting          ROAS Alert
                               |
                               v
                       Future LLM Analysis
```

The main principle is to first build the smallest trustworthy data product that answers the
business question.

The mandatory result is a reliable daily `fct_marketing_performance` model containing CAC and ROAS.

The architecture is designed so that the same foundation could later support additional
channels, campaign-level analysis, automation, and AI workflows without redesigning the whole
system.

The implementation intentionally avoids unnecessary infrastructure such as Kubernetes, Kafka, Airflow, or additional warehouse layers that are not required for the current use case.

## 2. Engineering Conventions

### Language

All source code must use English. This includes:

- variable names
- function names
- class names
- SQL aliases
- model names
- file names
- code comments
- docstrings
- log messages
- exception messages

Code comments must always be written in English. Project documentation may also be written in English to keep the repository internally consistent.

### Commit and Issue Naming

Issue titles follow the Conventional Commits format.

Examples:

- `feat(dbt): build marketing performance model`
- `test(dbt): add data quality checks`
- `docs(architecture): document infrastructure design`
- `chore: initialize project structure`

### Modeling Principles

- Each data model must have a clearly defined grain.
- Business logic should not be mixed into staging models.
- Source-specific cleaning belongs in staging.
- Reusable business logic belongs in intermediate models when necessary.
- Business-facing output belongs in the marketing mart.

The required final model is:

```
fct_marketing_performance
```

Its grain is:

> 1 row per calendar day

### Metric Definitions

For the simplified case study:

- `ROAS = revenue / ad_spend`
- `CAC = ad_spend / new_customers`

Because the provided mock data contains no attribution key connecting Shopify orders to Meta campaigns, these metrics must be described as **simplified blended metrics**. They must not be presented as true Meta-attributed ROAS or Meta-attributed CAC.
