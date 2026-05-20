# Ingestion Experiments

This document records small-scale review ingestion tests for Google Play Store and Apple App Store.


## Experiment 1: Google Play Store Review Collection

**Date:**  
2026-05-19

**Source:**  
Google Play Store

**App tested:**  
Spotify (`com.spotify.music`) 
Youtube (`com.google.android.youtube`)
Duolinguo (`com.duolingo`)

p.s. inside parentheses is package name for app on Google play


**Method:**  
Used a small Python script with `google-play-scraper` to collect recent English reviews from the U.S. region.

**Number of reviews requested:**  
100; 1000; 2000

**Number of reviews collected:**  
100; 1000; 2000

**Fields collected:**  
- source_platform
- app_id
- review_id
- review_text
- rating
- review_date
- app_version
- thumbs_up_count
- developer_response
- collected_at

**Initial observations:** 
THe script successfully collected 1000 reviews and saved them into a structured CSV file. The collected data includes review text, star ratings, review timestamps, app version information, thumbs-up counts, developer responses when available, and a collection timestamp.

The review structure appears usable for downstream cleaning and sentiment analysis. Several fields are consistently avaiable such as review text, rating, review date, and review ID. There are also missing fields, such as app version and developer response, may be missing for certain reviews.


## Experiment 2: Apple App Store Review Collection

**Date:**  
2026-05-19

**Source:**  
Apple App Store

**App tested:**  
Spotify (`324684580`)
Youtube (`544007664`)
Duolinguo (`570060128`)


**Method:**  
Used a small Python script with `app-store-web-scraper` to collect recent reviews from the U.S. Apple App Store.

**Number of reviews requested:**  
100 and 1000 respectively

**Number of reviews collected:**  
100 and 500 respectively

**Fields collected:**  
- source_platform
- app_id
- country
- review_id
- review_title
- review_text
- rating
- review_date
- user_name
- collected_at

**Initial observations:**  
The a`app-store-web-scraper` package successfully collected Apple App Store review data and saved it into a structured CSV file. The collected data includes review titles, review text, ratings, review timestamps, usernames, country, app ID, and collection timestamp. However, the script requested 1,000 reviews but only collected 500, which is consistent throughout the 3 different app tests. This suggests that the current Apple collection method may have a practical cap around 500 reviews per app-country query.



## Multi-App Scale Test Summary

| Platform | App | Reviews Requested | Reviews Collected | Runtime | Missing Fields | Initial Result |
|---|---:|---:|---:|---:|---|---|
| Google Play Store | Spotify (`com.spotify.music`) | 1,000 | 1,000 | 1.54 sec | `app_version`: 177 missing (17.7%); `developer_response`: 982 missing (98.2%) | Full 1,000-review collection successful |
| Google Play Store | Duolingo (`com.duolingo`) | 1,000 | 1,000 | 0.74 sec | `app_version`: 97 missing (9.7%); `developer_response`: 1,000 missing (100%) | Full 1,000-review collection successful |
| Google Play Store | YouTube (`com.google.android.youtube`) | 1,000 | 1,000 | 2.30 sec | `app_version`: 10 missing (1.0%); `developer_response`: 1,000 missing (100%) | Full 1,000-review collection successful |
| Apple App Store | Spotify (`324684580`) | 1,000 | 500 | 4.12 sec | No missing values in current fields | Structured collection successful, but capped at 500 |
| Apple App Store | Duolingo (`570060128`) | 1,000 | 500 | 2.96 sec | No missing values in current fields | Structured collection successful, but capped at 500 |
| Apple App Store | YouTube | 1,000 | 500 | 5.74 sec | No missing values in current fields | Structured collection successful, but capped at 500 |

## Preliminary Findings

**Ingestion stability:**  
Google Play Store appears more stable for larger-scale ingestion in the current tests. Across tested apps, it successfully returned the full requested 2,000 reviews. Apple App Store also produced clean structured outputs using `app-store-web-scraper`, but it consistently returned 500 reviews when 1,000 were requested, suggesting a practical limit in the current collection method.

**Realistic scale:**  
Google Play currently supports at least 2,000 reviews per app in the prototype tests, making it stronger for the first primary data source. Apple App Store appears feasible at the 500-review-per-app-country level, but may require multi-country collection, official API access, or another approved method to scale further.

**Metadata quality:**  
Google Play provides richer technical metadata, including app version and thumbs-up count, though optional fields such as developer response are mostly missing and app version can be missing for some reviews. Apple App Store provides clean and complete fields in the current output schema, including review title, review text, rating, review date, user name, country, and collection timestamp, but it does not currently include app version or engagement metadata.

**Review structure usability:**  
Both sources generate structured CSV outputs that are usable for downstream cleaning and sentiment analysis. The main cleaning challenges are typical of user-generated content: multilingual comments, emojis, very short reviews, informal spelling, and noisy or low-information text.
