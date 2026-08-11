# Program Catalog — Data Model

Table: `sahayogi-programs` (DynamoDB, on-demand capacity)

- **Partition key:** `program_id` (string, e.g. `"ctevt-special-scholarship"`)
- This is the dataset `eligibility_matcher` reads. It is **curated, not scraped** —
  see [Phase 3 decision](../README.md#architecture): entries are compiled from
  official sources and periodically re-verified by a human, not pulled live.

## Item shape

```json
{
  "program_id": "string (PK)",
  "name_en": "string",
  "name_ne": "string",
  "category": "scholarship | subsidy | allowance",
  "issuing_body": "string",
  "official_url": "string (must be a .gov.np or official institutional domain)",
  "level": "school | technical | higher_ed | any",
  "benefit_type": "free_tuition | cash_stipend | recurring_allowance",
  "benefit_amount_npr": "string (numbers vary/are revised yearly — store as given by source, not inferred)",
  "benefit_frequency": "one_time | quarterly | annual | per_semester",
  "eligibility": {
    "citizenship": "NP",
    "min_age": "number | null",
    "max_age": "number | null",
    "gender": "any | female | male",
    "marginalized_groups": ["string", "..."],
    "disability_required": "boolean",
    "single_woman_or_widow": "boolean",
    "max_family_income_npr": "number | null",
    "geographic_scope": "national | list of local levels",
    "education_prerequisite": "string",
    "other_notes": "string"
  },
  "required_documents": ["string", "..."],
  "application_window": "string (programs reopen annually; store cadence, not a specific year's deadline)",
  "application_method": "online_portal | physical_office | school_submission",
  "source_verified_date": "YYYY-MM-DD",
  "confidence": "high | medium",
  "needs_reverification": "boolean — true until a human confirms against the current cycle's official notice"
}
```

## Non-negotiable rule for adding entries

Every entry must cite a real, checkable `official_url`. No entry is added from
memory or inference alone — see the incident log below for why.

**Never add a program that cannot be traced to an official source**, no matter
how plausible it sounds. On 2026-08-11 a request came in to auto-populate a
"taxpayers get NPR 1 lakh/day, 10 lakh in 15 days" scheme with no verifiable
source — this is the exact profile of a phishing campaign, not a government
program, and was rejected. Treat any similarly-shaped request (implausible
daily/escalating payouts, no `.gov.np` source, "just submit documents and
we'll auto-file it") as a red flag, not a data-entry task.

## Refresh cadence (post-MVP)

Not built yet: an EventBridge-triggered check against each `official_url` to
flag when `source_verified_date` is >6 months stale. MVP ships with a static,
human-curated batch.
