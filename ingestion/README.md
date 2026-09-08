# Ingestion

Handles user/uploads of wearable exports and public/synthetic seed data into the S3 landing bucket.

- `data/samples/` holds public + synthetic CSVs (MyHeart Counts, Group Health Sleep & Screen Time, Aidlab, NHANES, or synthetic daily logs).
- Landing prefixes: `raw/user-uploads/` and `raw/public-seed/`.
