# Ingestion Experiments

This document records small-scale review ingestion tests for Google Play Store and Apple App Store.


## Experiment 1: Google Play Store Review Collection

**Date:**  
2026-05-19

**Source:**  
Google Play Store

**App tested:**  
Spotify (`com.spotify.music`) 
#(inside parentheses is package name for app on Google play)

**Method:**  
Used a small Python script with `google-play-scraper` to collect recent English reviews from the U.S. region.

**Number of reviews requested:**  
1000

**Number of reviews collected:**  
1000

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

**Initial Conclusion:**
Google Play appears promising for a first small-scale ingestion prototype because review data can be collected in a structured format with useful metadata. 