# SupplyChain360

**Enterprise Supply Chain & Logistics Intelligence Platform**

An end-to-end data engineering + analytics project that simulates the data
ecosystem of a large-scale e-commerce company: multi-source ingestion,
validation, ETL, PySpark processing, a PostgreSQL star-schema warehouse,
Airflow orchestration, and Excel / Power BI reporting.

---

## Project Status

| Phase | Name | Status |
|-------|------|--------|
| 0 | Project Setup | ✅ Complete |

---

## Project Architecture

```text
CSV / Excel / JSON / REST APIs
            │
            ▼
   Python Data Ingestion
            │
            ▼
        Raw Layer
            │
            ▼
    Data Validation
            │
            ▼
     ETL Processing
            │
            ▼
 PySpark Transformations
            │
            ▼
 PostgreSQL Data Warehouse
            │
   ┌────────┴─────────┐
   ▼                   ▼
Excel Analytics   Power BI Dashboards
            │
            ▼
 Apache Airflow Automation
```

## Folder Structure

```text
SupplyChain360/
├── data/{raw,processed,warehouse,archive}
├── notebooks/
├── src/{ingestion,validation,etl,pyspark,warehouse,analytics,reporting,automation,utils}
├── airflow/{dags,plugins}
├── sql/
├── dashboards/{Excel,PowerBI}
├── docs/
├── logs/
├── docker/
├── tests/
├── config/
├── requirements.txt
├── docker-compose.yml
├── .env.example
└── README.md
```

## Tech Stack

**Data Engineering:** Python, Pandas, NumPy, SQL, PostgreSQL, PySpark, Apache Airflow, Docker, Git & GitHub
**Analytics:** Excel (Power Query, Pivot Tables, Advanced Functions), Power BI, DAX
**APIs:** Weather, Exchange Rates, Public Holidays (fuel price / product info optional)

## License

MIT — see [`LICENSE`](LICENSE).
