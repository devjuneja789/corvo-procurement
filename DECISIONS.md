# Procurement decisions and assumptions

## Dates and rule precedence

New items are handled before grouping and the ordered section 5 rules. Capex takes precedence over contract POs. Supplier status is a global eligibility constraint. A contract considered for Capex valuation does not consume ceiling because no contract PO is placed.

Requirement date is the first line's date. Creation-time sorting uses PR number and numeric line number to break ties. Clubbing uses inclusive calendar-date differences (14 and ±7); consolidation uses inclusive elapsed time (24 hours). Neither window rolls forward. A line chooses the earliest eligible existing group. A requirement chooses the earliest eligible PO. All timestamps are interpreted as company-local, naive timestamps in the input; audit events use UTC. Chat timestamps use Asia/Kolkata.

Historical lookbacks include their lower bound and exclude the requirement/as-of date. Date-only historical POs on that date cannot reliably establish that they predate the requirement. Contract validity is inclusive at both ends. Future contracts are excluded from preferred-list evidence until their start date.

The policy version selected for a batch is the upper bound of its approved policy timeline. Earlier requirements use the most recent approved earlier version effective on their date. A group keeps the policy effective on its first line, including its clubbing settings, even if later member lines cross an amendment date. Selecting v5.0 always isolates the baseline. Runs pin the selected timeline, datasets, original PR lines, results and explanations. Policy preview can test a draft without activating it.

## Matching and data quality

An explicit valid item code takes precedence over text. An unknown explicit code is a validation failure rather than permission to substitute a different item. Without a code, normalize case, separators, common procurement abbreviations, and incidental phrases. Require compatible numeric/specification tokens. Use deterministic token coverage and a confidence margin; uncertain batch matches become NEW, while chat asks for clarification among candidates. The matching algorithm does not refer to particular PR identities.

New items remain individual requirements and have no suggested suppliers. They require the requester's estimate. Units must match the item master; no conversion factor is invented. Zero/negative quantities, invalid dates, unknown plants, invalid urgencies, missing estimates, or duplicate PR identities produce NOT_PROCESSED rows with reasons, blank purchasing fields and a policy version. They are never silently omitted. Structural CSV errors reject the upload so the user can repair it.

Master uploads validate before replacement, including foreign keys against existing dependent tables. Load items, suppliers, plants, contract register, contract lines, then history. Register/PDF overlap is not imported twice. Newly added PDF contracts start consumed value at zero; existing registered contracts retain the snapshot's consumed value. Buyers review extracted contract terms before saving. Scanned PDFs require external OCR or manual entry. PDFs whose text cannot be extracted reliably fail visibly.

## Contract ceilings and valuation

Use the lowest-rate applicable contract that covers the entire group's quantity within remaining ceiling. Equal rates break by contract ID. Do not partially fulfill a group against a contract. If no applicable contract has room, use the lowest applicable contract rate for valuation, then apply the remaining route rules. Otherwise use the most recent item PO within 365 days, then standard price. Equal-date PO prices break by PO number descending.

Valuation POs need not have an Active supplier: clause 3.1 does not impose that constraint. The purchase-history gate for spot/emergency POs does require an Active supplier. Only Active suppliers can be selected or suggested. Section 3.1's valuation price may differ from section 6.3's actual spot/emergency PO reference price. Keep the group valuation and actual PO price distinct.

Use Decimal for quantities, rates and multiplication; compare unrounded values with limits. Format exported amounts to two decimal places with half-up rounding. Worked-example displayed whole-rupee prices are illustrative; do not multiply rounded displayed prices. Example summaries can describe multiple requirements with one value or ID; source data and the explicit anchored rules determine grouping and amounts.

Every batch replay has an isolated contract-consumption ledger initialized from its pinned data snapshot. Run 2 can explicitly reuse Run 1's dataset snapshot. Simulated POs never become historical evidence or consume another simulation's ceiling. Final buyer approval records a separate transactional reservation ledger against the live contract cap. Duplicate purchasing documents for the same PR identity are blocked across runs. Export decisions are proposed engine decisions and do not require actually approving every PO during the blind test.

## Preferred supplier ranking

Eligibility: Active supplier, plus a PO for the item in 548 days before the date or an item contract started by that date, including expired contracts.

Score = 35 × normalized PO frequency + 25 × recency + 15 × contract evidence + 15 × on-time fraction + 10 × quality/5. Normalize PO count by the largest eligible supplier count for that item (minimum divisor 1). Recency = 1 within 90 days, 0.5 within 365, otherwise 0; no recent PO gives 0. Contract evidence is 1 if an eligible historical contract exists, otherwise 0. Delivery and quality use the supplied supplier master ratings, which are the available snapshot. Break score ties by latest PO date descending, then supplier ID ascending. Expose all components and evidence to buyers. The method reproduces the order of all three illustrative lists.

Reference price uses that supplier's latest item PO in 548 days; otherwise its most recent started item contract. Equal contract start dates break by contract ID descending. Sourcing first uses the preferred list, then other Active category suppliers ranked by delivery/100 + quality/5, with supplier ID as a tie-breaker. Do not pad with ineligible suppliers if fewer than 3 or 5 exist. Category top-ups are suggestions, not automatically eligible preferred suppliers. Preferred CSV exports at most three eligible suppliers per item; items without eligible suppliers have no ranking rows.

## Policy updates

All thresholds, time windows, ranking weights, rule order, predicates and route outcomes are versioned data. A bounded allowlisted interpreter supports nested all/any, equality, inequality, ordering and membership over item type, category, plant, value, quantity, urgency, usable contract, purchase history and item code. No uploaded code is evaluated. Unsupported concepts fail rather than being silently ignored.

AI may propose a complete policy from a document or chat description. The server validates it, shows a plain-language diff, and stores an immutable draft. Approval changes its lifecycle status, preserving its body, source and effective date. Version IDs are unique. Natural-language interpretation requires a server-side AI key; JSON policy uploads and editing work without one. Unsupported or incomplete extraction cannot activate itself. Document text is treated as untrusted content.

## Buyer actions, security, and scope

Approval of a consolidated PO approves all its member requirements together and creates a persisted purchasing document. Sourcing approvals create an internal RFQ/RFP record. No external supplier communication or ordering integration is implied. Overrides require a replacement route and written reason; PO overrides also require an Active supplier and price. Contract PO overrides must be reprocessed through the contract engine to preserve ceiling controls. The original engine output and blind-test CSV stay immutable; override documents and audit events retain the replacement decision separately.

This small deployment uses buyer and requester roles with separately configured shared passwords and HTTP Basic authentication over HTTPS. Role names identify actors; this is not individual enterprise identity. Browser credentials stay in sessionStorage. There is no default hosted password. Local no-password mode is for development only. Requesters can create chat PRs and cannot access buyer APIs. Cross-origin writes are rejected. No task kit or runtime database is in Git or the Docker build context. The hosted architecture uses persistent storage and a single instance; this is intentionally not a horizontally scaled procurement system.

## Blind-test amendment correction

Amendment No. 1 is recorded as `5.1-reviewed` because the initially approved `5.1` record retained the original v5.0 rules. The correction was made through the app's existing structured policy editor and approval workflow, effective 1 December 2026, without code changes. The original approved record remains preserved.

The Packaging change is interpreted as a reduction to the spot-PO limit in rule 5.4; existing contract and emergency rules remain unchanged. The new CHK1 Electrical Spares sourcing rules run immediately after contract rule 5.2, before emergency and spot rules. The RFQ/RFP threshold is INR 800,000. Requirements retain the policy effective on their first line's date.
