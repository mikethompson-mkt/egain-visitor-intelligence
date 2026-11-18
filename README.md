# eGain Visitor Intelligence

A searchable, evidence-based website engagement dashboard for sales representatives, built from the provided eGain.com February 2025 visitor request log.

## What it does

- Search by IP address or visited page path
- Filter IPs by engagement tier and number of active days
- Rank activity with a transparent, reproducible intent heuristic
- Flag common crawler / automation user agents and suppress bot-heavy IPs by default
- Inspect each IP's timestamped request evidence, topics, referrers, and suggested next action
- View daily traffic, content interests, and popular product pages
- Export an individual IP's recent activity as CSV
- Optionally upload permissioned IP-to-company enrichment as CSV, search by company name/domain, inspect grouped account signals and provider provenance, and export evidence

**Important:** The supplied `Domain` field identifies the eGain website host, not the visitor's company. No account, individual, or buying decision is identified from these logs. IP-to-company enrichment is deliberately not fabricated.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The provided `data/visitors.sqlite.gz` is precomputed, so the source workbook is not required to run the app.

## Rebuild the database

```bash
python build_data.py "path/to/Website visitor IP address log file.xlsx" --output data/visitors.sqlite
```

Compress the output for deployment with `gzip -k data/visitors.sqlite` (or Python gzip). The processing script streams the workbook using XML parsing to avoid loading the full spreadsheet into memory. It preserves the seven source fields needed for analysis, but the deployed database stores IP, timestamp, URL, referral, derived topic, score weight, and automation flag rather than full user-agent strings. This is intentional data minimization.

## Deploy for 15+ days

1. Create a GitHub repository and upload `app.py`, `build_data.py`, `requirements.txt`, `README.md`, and `data/visitors.sqlite.gz`. The compressed database avoids GitHub's 100 MB per-file limit.
2. Go to https://share.streamlit.io and select **Create app**, pointing to your GitHub repository, `main` branch, `app.py` entry point.
3. Set public access as required for the evaluation, and verify the URL in a private browser window.
4. Keep the repository and hosting active for at least 15 days after submission. Confirm hosting availability; free tiers may sleep when idle.

**Privacy caution:** The compressed deployed SQLite database contains raw IP addresses from the provided source. Obtain permission before publishing source-derived IP data publicly; if necessary, use a private app or anonymize IPs and limit access. Do not publish the original spreadsheet without authorization.

## Scoring

For each IP, score = min(100, min(relevant requests,12)×3 + min(active relevant days,6)×6 + min(relevant topics,5)×8 + min(weighted page points,40)×0.35). If more than 80% of requests are explicitly bot-flagged, cap the score at 15. High ≥65, Medium ≥30, otherwise Low.

Relevant page topics are classified by URL keywords. Generic corporate pages, assets, and homepage requests receive no intent points. Bot flagging uses user-agent patterns and non-GET methods; it is imperfect. There is no person-level attribution, sessionization, or verified company mapping.

## Architecture

`XLSX` → streaming `build_data.py` (normalize, classify, flag) → indexed `SQLite` (`activity`, `visitors`, `metadata`) → `Streamlit` (SQL filters, KPIs, account explorer, evidence drill-down, charts).

## Possible production enhancements

- Permissioned IP-to-company enrichment with source, confidence, and last-verified timestamp
- CRM match/ownership checks and Salesforce integration
- User/session identifiers where lawfully available
- More robust crawler detection using ASN and traffic-pattern analysis
- Authenticated access, audit logs, data retention rules, scheduled ETL, and monitoring

## Evaluation caveats

The sample covers a historical February 2025 period. This prototype provides **interest indicators**, not verified account/contact identity, purchase intent, or conversion predictions. Sales outreach should be based on verified company identification and CRM context.

## Optional company intelligence

Open the **Company intelligence** tab and upload a CSV with the columns in `company_enrichment_template.csv`:

`ip,company,company_domain,provider,confidence,lookup_date`

Only populate this file with IP-to-company associations obtained from an authorized, reputable enrichment provider or a separately validated internal source. Do not enter fictitious company names. `confidence` is the provider's label (not a guarantee of identity); `lookup_date` should be an ISO date (YYYY-MM-DD). The app matches those IPs to the historical website data and summarizes the associated activity. An uploaded CSV stays in the Streamlit session and is not saved by the app. The original logs have **no company identities**; without enrichment, the tab clearly says so.

A match is not proof that a particular person or employee visited the site. Dynamic IP assignments, VPNs, proxies, shared networks, and cloud providers limit confidence. Check source, date, ISP/cloud matches, and CRM before any sales action.

For a public demo, avoid uploading confidential enrichment or personal data. Use only authorized data and follow applicable privacy and data-handling requirements.
