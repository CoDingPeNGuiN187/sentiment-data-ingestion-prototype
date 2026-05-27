# SQL Schema Design

## Goal

The goal of this schema is to store reviews from multiple google play apps. 

## Design Principles

1. **Extensibility across multiple apps**
App-level info is stored separately so that future apps can be added without changing the review table structure. 

2. **Separation of raw data and derived features**
Raw review data, such as review text, rating, review date, app version, and thumbs-up counts shold be stored separately from derived quality features, such as word count, duplicate flags, and low-signal lables. 

3. **Ingestion run tracking**
Each data collection run should be tracked separately. In this way, we could record how many reviews were requested, how many were collected, runtime, and whether the run succeedded. 

4. **Deduplication and data integrity**
The schema should prevent the same platform review from being inserted multiple times for the same app.

5. **Future cleaning and analysis support**
The schema should support downstream cleaning, exploratory analysis, and quality checks before building further analytics layers.

## Table Overview

The schema contains four main tables:

| Table | Purpose |
|---|---|
| `apps` | Stores app-level metadata, such as platform, app name, Google Play package ID, country, and language. |
| `ingestion_runs` | Stores metadata about each data collection run, such as requested count, collected count, runtime, status, and timestamps. |
| `reviews` | Stores raw review-level data collected from Google Play. |
| `review_quality_features` | Stores derived review-level quality and cleaning features, such as review length, duplicate flags, and low-signal indicators. |

---

## Table 1: `apps`

The `apps` table stores one record for each app/source configuration.

Example app records could include:

| app_id | platform | platform_app_id | app_name | country | language |
|---:|---|---|---|---|---|
| 1 | Google Play | com.openai.chatgpt | ChatGPT | us | en |
| 2 | Google Play | com.spotify.music | Spotify | us | en |
| 3 | Google Play | com.duolingo | Duolingo | us | en |

- `app_id` is the internal database ID.
- `platform_app_id` stores the app ID from the original platform, such as the Google Play package name.
- `platform`, `platform_app_id`, `country`, and `language` are unique together to avoid duplicate app records for the same source configuration.

---

## Table 2: `ingestion_runs`

The `ingestion_runs` table stores metadata about each review collection run.

Example ingestion run:

| ingestion_run_id | app_id | requested_count | collected_count | runtime_seconds | status |
|---:|---:|---:|---:|---:|---|
| 1 | 1 | 25000 | 25000 | 11.29 | success |

- `app_id` is a foreign key referencing `apps(app_id)`.
- This makes it possible to trace each review back to a specific collection run.
- `status` can store values such as `success`, `failed`, or `partial_success`.

---

## Table 3: `reviews`

The `reviews` table stores the raw review-level data collected from Google Play.

Fields include:

- Platform review ID
- Review text
- Rating
- Review date
- App version
- Thumbs-up count
- Developer response
- Collection timestamp

Key design choices:

- `review_id` is the internal database ID.
- `platform_review_id` stores the original review ID from Google Play.
- `app_id` connects each review to the corresponding app.
- `ingestion_run_id` connects each review to the collection run that produced it.
- `UNIQUE (app_id, platform_review_id)` prevents duplicate reviews for the same app.
- `rating` is constrained to be between 1 and 5.
- `app_version` and `developer_response` are nullable because the EDA showed that these fields may be missing.

From the ChatGPT 25k EDA, core fields such as `review_id`, `review_text`, `rating`, `review_date`, `thumbs_up_count`, and `collected_at` were complete. However, `app_version` had missing values, and `developer_response` was missing for all collected reviews. Therefore, these optional metadata fields should not be required.

---

## Table 4: `review_quality_features`

The `review_quality_features` table stores derived features created during cleaning or EDA.

These fields are not part of the raw review data itself. They are calculated after collection.

Examples include:

- Review character length
- Review word count
- Whether the review is very short
- Whether the review is generic text
- Whether the review is low-signal
- Whether the review text is duplicated
- Detected language

Key design choices:

- `review_id` is a foreign key referencing `reviews(review_id)`.
- This creates a one-to-one or one-to-many relationship between a review and its processed quality features.
- `processed_at` records when these features were generated.

---
## Relationship Between Tables

The tables are connected as follows:

```text
apps
  ├── ingestion_runs
  └── reviews
          └── review_quality_features
