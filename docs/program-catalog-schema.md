# Program Catalog — Data Model

Table: `sahayogi-programs` (DynamoDB, on-demand capacity)

- **Partition key:** `program_id` (string, e.g. `"ctevt-special-scholarship"`)
- This is the dataset `eligibility_matcher` reads. It is **curated, not scraped** —
  see [Phase 3 decision](../README.md#architecture): entries are compiled from
  official sources and periodically re-verified by a human, not pulled live.

## Multi-country design

The catalog is **country-agnostic by architecture, Nepal-only by data**. Every
entry carries a `country` field (ISO 3166-1 alpha-2) and `eligibility_matcher`
filters on it — an applicant asking about a country with zero catalog entries
gets an honest "not covered yet," never a guess. Adding a second country is a
data-curation task (research + verify + add entries, same rigor as below), not
an architecture change. Nepal is the fully-verified flagship deployment; we
deliberately have not added other countries without doing the same sourcing
work — see the non-negotiable rule below for why that matters here
specifically.

## Item shape

```json
{
  "program_id": "string (PK)",
  "country": "string (ISO 3166-1 alpha-2, e.g. \"NP\")",
  "name_en": "string",
  "name_ne": "string",
  "category": "scholarship | subsidy | allowance",
  "issuing_body": "string",
  "official_url": "string (must be an official government or government-recognized institutional domain for this program's country)",
  "level": "school | technical | higher_ed | any",
  "benefit_type": "free_tuition | cash_stipend | recurring_allowance",
  "benefit_amount": "string (currency embedded in the text, e.g. 'NPR 4,000/month' — numbers vary/are revised yearly, store as given by source, not inferred)",
  "benefit_frequency": "one_time | quarterly | annual | per_semester",
  "eligibility": {
    "citizenship": "string (ISO 3166-1 alpha-2 — the citizenship required to qualify; usually but not always equal to the program's `country`)",
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
