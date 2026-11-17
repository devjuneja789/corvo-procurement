# Corvo procurement workspace

A full-stack procurement app with conversational PR intake, deterministic policy decisions, versioned document/chat policy updates, batch replay, a buyer workspace, and exact CSV exports.

## Run locally

Requires Python 3.12+. The core uses the standard library. Install the pinned runtime dependencies for reliable PDF extraction and timezone support across Linux, Windows, and Docker.

```bash
python3 -m app.server
```

Open **http://localhost:8000**. Local mode permits buyer access when `APP_PASSWORD` is unset. Stop with Ctrl+C. All data persists in ignored `private_data/app.sqlite3`.

Install runtime dependencies before deploying or running on a machine without system timezone data:

```bash
python3 -m pip install -r requirements.txt
```

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

## Deploy to Render

The included [render.yaml](render.yaml) defines a Docker web service, health check, persistent disk and disabled automatic deployments. This blueprint selects a **paid service with a persistent disk** so uploads and run snapshots survive restart; review Render's current charges before creating it. See [Render's Blueprint reference](https://render.com/docs/blueprint-spec) and [persistent disk documentation](https://render.com/docs/disks).

1. Create a **public GitHub repository** and push the source files. Keep the kit, implementation plan, credentials, database and private exports excluded. `git status --short --ignored` shows the exclusions. Check your configured remote with `git remote -v`. Create the GitHub repository empty (without a generated README) before pushing this source.
2. In Render, select **New → Blueprint**, connect that repository, and apply `render.yaml`. The blueprint is the supported configuration; do not deploy this as a static site.
3. Set `APP_PASSWORD` for the **buyer** login and a different `REQUESTER_PASSWORD` for the **requester** login. Set `OPENROUTER_API_KEY` to enable natural-language policy amendments. Keep `DATABASE_PATH=/var/data/app.sqlite3`. Render supplies `PORT`.
4. Deploy, then open the returned `https://…onrender.com` URL. Upload the private kit through the UI. Verify a sample batch, chat confirmation, a document amendment, and downloaded CSVs in the deployed app.
5. Keep the service and persistent disk available through the review. Share buyer access privately with the evaluators if needed. Do not place login passwords in the public README.

Auto-deploy is disabled to protect the frozen build. Make any required deployments manually **before** the deadline. Do not change code or deploy different code during the blind test.

The local environment used to build this app blocks socket creation, package-registry networking, and Docker's WSL integration. The actual API dispatcher, database operations and engine were tested in-process; a real browser session, Docker image build, live AI call and hosted deployment still need verification in an unrestricted environment. These checks do not substitute for the hosted smoke test below.

## Before the first push and deployment

Review the public file list before staging. Original kit PDFs/CSVs, newly downloaded PDF/CSV/XLS inputs, `.env`, local databases and the implementation plan are ignored. Synthetic demo CSVs and the three required `submission/` CSVs are explicit exceptions. Never force-add private task inputs.

```bash
git status --short --ignored
git add .
git diff --cached --name-only
git diff --cached --check
```

Inspect that list, then create the initial commit and push to your own public repository. Do not publish passwords or API keys. Commit the source before connecting the Render blueprint.

After deploying, verify these steps before submitting your links:

1. `/health` returns `{"status":"ok"}`; the main page loads and buyer login works.
2. Upload the private datasets and PDF-only contracts; process the sample batch and check line counts, exceptions and CSV columns.
3. Complete a chat PR, review it, approve it, and inspect its persisted purchasing document.
4. Upload an amendment, review/approve it, and rerun the same batch from the baseline snapshot. Confirm changed decisions and stable baseline replay.
5. Restart the Render service and confirm uploads, policies and saved runs persist. Test requester access separately.
6. Verify a live OpenRouter request using your server-side key. The default model is accessed through OpenRouter; it does not require a separate OpenAI key. A funded/eligible OpenRouter account and a JSON-capable model are required.

GitHub Actions runs the tests, JavaScript syntax check and Docker build for source changes. A passing local test suite alone does not verify the image build or live service.

## Blind-test runbook

Build freeze: **Thursday 19 November 2026, 10:00 AM IST** (04:30 UTC). Submit your public repository and working hosted link using the organizer's form before then.

1. Import replacement master/contract data if provided. Upload the blind PR batch and select **v5.0**. Label it Run 1 and process. Download **dev_juneja__run1.csv**.
2. Upload the amendment in Policy versions, review its extracted rules/effective date, preview impact, and approve it. Use the app only; do not change code.
3. Re-upload the same PR batch in Buyer workspace, select the amended policy, and choose **Run 1's snapshot** as starting data. Process Run 2 and download **dev_juneja__run2.csv**.
4. In Preferred suppliers, choose the requested as-of date, relevant approved policy, and the same data snapshot. Download **dev_juneja__preferred.csv**.
5. Place only these three outputs in `submission/`. Inspect the Git diff, then commit and push those CSVs before **12:00 noon IST** (06:30 UTC). Do not commit private input files or code changes.

Batch export reflects proposed engine decisions; you do not need to approve every PO to produce the blind-test outputs. Runs have isolated ceiling ledgers. Run 2 must use Run 1's starting snapshot for a fair comparison.

## API

Buyer routes require HTTP Basic auth when `APP_PASSWORD` is configured. Use username `buyer`; employee chat uses username `requester`. Each role has its configured password. Local development can omit credentials when `APP_PASSWORD` is absent. Hosted configuration refuses to run authenticated actions without an explicit password.

| Route | Purpose |
|---|---|
| `GET /health` | Deployment health |
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

See [DECISIONS.md](DECISIONS.md) for ambiguity resolutions and ranking details, and [APPROACH.md](APPROACH.md) for architecture and actual AI usage. The implementation plan is intentionally ignored.
