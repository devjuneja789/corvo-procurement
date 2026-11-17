# Corvo procurement workspace

A full-stack procurement app with conversational PR intake, deterministic policy decisions, versioned document/chat policy updates, batch replay, a buyer workspace, and exact CSV exports.

## Run locally

Requires Python 3.12+. The core uses the standard library. Install the pinned runtime dependencies for reliable PDF extraction and timezone support across Linux, Windows, and Docker.

```bash
python3 -m pip install -r requirements.txt
python3 -m app.server
```

Open **http://localhost:8000**. Local mode permits buyer access when `APP_PASSWORD` is unset. Stop with Ctrl+C. All data persists in ignored `private_data/app.sqlite3`.

Alternatively, with Docker Desktop running and WSL integration enabled:

```bash
docker compose up --build
```

Docker stores the database in the `procurement-data` volume. Copy `.env.example` to `.env` before Docker startup to set passwords and the optional AI key. For plain Python, set the same variables in your terminal environment; Python does not automatically load `.env`.

## Load data

The task kit is deliberately excluded from Git and Docker. It is not bundled with the public app.

In **Data & contracts**, upload CSVs in this order:

1. Item master → `items`
2. Supplier master → `suppliers`
3. Plants → `plants`
4. Contract register → `contracts`
5. Contract lines → `contract_lines`
6. PO history → `history`

Then extract, review, and save the signed contracts that are absent from the register. Already registered IDs are rejected. Manually entering reviewed contract JSON is also supported. For local setup only, this helper reads the kit from an external path and imports the two PDF-only contracts automatically:

```bash
python3 scripts/import_kit.py /path/to/private/kit
```

For a public-safe demo, use a fresh database and seed the synthetic files in `demo/`:

```bash
python3 scripts/seed_demo.py
```

The demo uses fictional SITE-A/SITE-B and DEMO-A identifiers unrelated to the kit. Upload `demo/requests.csv`, then `demo/amendment.json` to rehearse the update flow. The seed refuses to overwrite existing records. Do not import demo data over the kit database.

## Use the app

- **Raise a request:** describe the purchase. The assistant asks for quantity, plant, need-by date, urgency, and an estimate for new items. Confirm before creating the PR.
- **Buyer workspace:** upload the sample-format PR CSV, select an approved policy, and process. Inspect requirement members, route, value, source clause, supplier and price. Approve a consolidated PO or sourcing document, or record an override with a reason. Purchasing documents are internal persisted records; no external order is sent.
- **Preferred suppliers:** choose an as-of date, policy and optionally a saved-run data snapshot. Inspect score components and evidence; download the top-three CSV.
- **Policy versions:** upload PDF/text/JSON, describe an amendment, or edit the structured JSON policy. Include a unique version and effective date. Review the plain-language diff, preview impact on an existing run, and approve. Drafts do not affect purchasing.
- **Activity log:** inspect upload fingerprints, run activity, policy lifecycle and buyer actions.

`OPENROUTER_API_KEY` enables natural-language chat interpretation and policy/amendment interpretation. Set it on the server, never in frontend code or Git. `OPENROUTER_MODEL` defaults to `openai/gpt-4.1-mini`. Without a key, deterministic catalog chat and complete JSON policy upload/editing remain functional. Natural-language policy changes deliberately fail with a clear message rather than guessing rules. JSON policies are executable data interpreted by a bounded predicate engine, not uploaded code.

## API

Buyer routes require HTTP Basic auth when `APP_PASSWORD` is configured. Use username `buyer`; employee chat uses username `requester`. Each role has its configured password. Local development can omit credentials when `APP_PASSWORD` is absent. Hosted configuration refuses to run authenticated actions without an explicit password.

| Route | Purpose |
|---|---|
| `GET /health` | Service health |
| `GET /api/state` | Role, dataset summaries, policy versions, saved runs |
| `POST /api/data` | `{kind,csv}` validates and replaces a master dataset |
| `POST /api/document` | `{name,base64}` extracts document text |
| `POST /api/contract/draft` | `{text}` proposes contract fields/rates |
| `POST /api/contract/save` | `{contract,lines,source}` saves reviewed terms |
| `POST /api/process-batch` | `{csv,policy_id,label,snapshot_run_id?}` returns and saves decisions |
| `GET /api/run?id=…` | Run results and buyer actions |
| `GET /api/export?id=…` | Exact decisions CSV |
| `GET /api/preferred?date=YYYY-MM-DD&policy_id=…&run_id=…&csv=1` | Preferred-supplier CSV; omit csv for explanation JSON |
| `POST /api/policy/draft` | `{base_id,text}` interprets document/chat or JSON; `{base_id,policy}` accepts structured data |
| `POST /api/policy/preview` | `{run_id,policy_id}` compares a saved run under another policy |
| `POST /api/policy/activate` | `{id}` approves a draft version |
| `POST /api/chat` | `{session_id?,message}` conversational intake and confirmation |
| `POST /api/action` | `{run_id,group_id,action,comment?,override?}` creates purchasing document / override |
| `GET /api/documents` | Persisted PO and sourcing documents |
| `GET /api/audit` | Latest activity events |

`POST /api/process-batch` also accepts a raw `text/csv` body with `?policy_id=<id>` (JSON is recommended). There is no multipart requirement. JSON uploads are limited to 12 MB including base64 encoding. Examples of structured policy rules are in `demo/amendment.json`.

Output columns, in order:

```text
pr_no,pr_line,resolved_item_code,group_id,po_id,decision,route,supplier_id,unit_price,group_value_inr,suggested_supplier_ids,policy_version,reason
```

Preferred columns: `item_code,rank,supplier_id,reference_price`.

## Verification and design

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
python3 -m compileall -q app
```

The synthetic suite covers threshold and time boundaries, rule precedence, cumulative contract ceilings, replay isolation, supplier eligibility, date-aware policy selection, amendment preview/approval/replay, auth, overrides and purchasing-document persistence. Private kit checks account for every sample line, check worked decisions and compare the three example ranking orders. No supplied kit data is committed as test fixtures.

See [DECISIONS.md](DECISIONS.md) for ambiguity resolutions and ranking details, and [APPROACH.md](APPROACH.md) for architecture and actual AI usage.
