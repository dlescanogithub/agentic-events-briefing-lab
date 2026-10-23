# Rubric

Source of truth: `config/rubric.json`, version `2026-10-17.1`. The ranker refuses a file whose weights do not sum to 1.

## Score

Group floors, then a within-band score capped at 0.999 so a band cannot cross the next floor:

| Group | Floor |
| --- | --- |
| life_safety | 4.0 |
| property | 3.0 |
| quality_of_life | 2.0 |
| other | 1.0 |
| noise | 0.0 |

Within the band:

| Part | Weight |
| --- | --- |
| severity | 0.40 |
| recency | 0.25 |
| density | 0.20 |
| category | 0.15 |

- Recency uses the newest `created_at` in the batch as time zero, with a 24 hour half-life. The clock "now" is not used, so a snapshot ranks the same way later.
- Density counts other incidents that share geohash 6 and category group, only when `location_precision` is `rounded_2dp`. Borough centroids do not form clusters. Cap is 5 neighbors in the log scale.
- Category weight is the group's weight in the same JSON file.
- Tie break: higher score, then newer `created_at`, then ascending id.

The floor is what makes "life-safety never ranks below noise" true even if a noise row has severity 0.99 and a life-safety row is old. That is a hard constraint, not an accident of the weights.

## Category map (lab judgment)

This is not the City's taxonomy.

311, lowercased exact match, else a `noise` prefix, else `other`:

- life_safety: Hazardous Materials; Traffic Signal Condition (severity override 0.55)
- property: Electrical, Water Maintenance
- quality_of_life: Illegal Parking, Abandoned Vehicle, Homeless Person Assistance (category only; no person record), Residential Disposal Complaint, Dirty Condition
- noise: complaint type starting with "noise"
- other: anything else, including Non-Emergency Police Matter

NYPD `ofns_desc` keywords, first match wins:

- life_safety: ASSAULT, ROBBERY, RAPE, SEX CRIME, MURDER, HOMICIDE, WEAPON, ARSON, KIDNAP, MANSLAUGHTER
- property: LARCENY, BURGLARY, MISCHIEF, STOLEN, THEFT, FRAUD, FORGERY
- quality_of_life: HARRASS, HARASS, VEHICLE AND TRAFFIC, DISORDER, TRESPASS
- other: the rest, including DANGEROUS DRUGS

Severity hint for NYPD comes from `law_cat_cd`: FELONY 0.9, MISDEMEANOR 0.55, VIOLATION 0.3, default 0.4.

FDNY `incident_classification_group`:

- Structural Fires, Medical Emergencies, Medical MFAs → life_safety
- NonMedical Emergencies → property
- NonMedical MFAs → other

Alarm severity: First Alarm 0.45, All Hands Working 0.7, then up to Fifth Alarm 1.0. Structural fires take at least 0.7.

## What this rubric does not claim

It does not claim the City would sort the same way. It does not claim a desk has accepted the map. Changing a floor requires the eval in `docs/METRICS.md` to be re-run.
