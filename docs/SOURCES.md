# Sources and provenance

Verified on **2026-09-13**. The official CMS machine-readable catalog identified **2026Q1** as the latest available release at retrieval. The analysis uses 2024Q2–2026Q1.

| Resource | Verified location |
| --- | --- |
| Dataset | https://data.cms.gov/quality-of-care/payroll-based-journal-daily-nurse-staffing |
| Catalog | https://data.cms.gov/data.json |
| Current release resources | https://data.cms.gov/data-api/v1/dataset-resources/6e5d5e28-66fd-41bc-a36c-db54dcbffd3e |
| Current dictionary, 2023-06-02 | https://data.cms.gov/sites/default/files/2023-06/Payroll%20Based%20Journal%20Daily%20Nursing%20Staffing%20Data%20Dictionary.pdf |
| Current methodology, July 2023 | https://data.cms.gov/sites/default/files/2023-06/PBJ_PUF_Documentation_July_2023.pdf |
| API guide, May 2024 | https://data.cms.gov/sites/default/files/2024-05/39b98adf-b5e0-4487-a19e-4dc5c1503d41/API%20Guide%20Formatted%201_5.pdf |

The resources endpoint linked the June 2023 dictionary and July 2023 methodology. Original raw copies are archived locally by the project owner and excluded from this repository. The published [manifest](../data/manifest.json) records every quarter's exact API request URL, timestamp, reporting period, row count, columns and source schema version. The original raw pages contain all 33 columns and unchanged response bytes. State filtering is server-side, followed by a local state check. The original archived catalog also records national CSV download URLs and release modification dates. See [reproduction](REPRODUCTION.md) for reacquisition and the limits of restoring a historical snapshot.

CMS describes facility-day paid staffing hours and retrospectively derived MDS census. Public releases are quarterly, and CMS applies facility-level quarterly inclusion/exclusion criteria. A missing facility-quarter is not a zero staffing observation. A reported zero indicates no reported hours for that category/day and is retained as observed utilization. Extreme daily observations can remain. These source limitations come from the [CMS methodology](https://data.cms.gov/sites/default/files/2023-06/PBJ_PUF_Documentation_July_2023.pdf).

The project assumes a daily internal feed and availability of historical census solely for replay. Publication delays, retrospective revisions, and MDS derivation mean this is not a genuine vintage backtest against information available from CMS at T. No future census or staffing values are used by the implemented feature pipeline.

API discovery, fixed-quarter references, pagination up to 5,000 rows, state filters and sorting follow the [CMS API guide](https://data.cms.gov/sites/default/files/2024-05/39b98adf-b5e0-4487-a19e-4dc5c1503d41/API%20Guide%20Formatted%201_5.pdf). Responses and documents are treated only as data. No embedded instructions are executed.

Government data attribution does not imply CMS endorsement. This project is independent and has no Ascension affiliation.
