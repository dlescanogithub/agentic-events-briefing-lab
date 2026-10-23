# Data sources

Access date for the pages and SODA calls below: **2026-10-17**.

Code in this repository is MIT. These rows are not. The same boundary is in the repository `NOTICE` file. Dataset metadata returned `license: null` on the Socrata view API. No open-source data license was stated there. Use is subject to the City of New York terms. This repo does not relicense the snapshots.

## Terms

- NYC.gov Terms of Use, accessed 2026-10-17: https://www.nyc.gov/home/terms-of-use.page
  The materials are offered "as is" and "as available", without a warranty of accuracy or completeness (section VI of that page as fetched that day).
- NYC Open Data overview, accessed 2026-10-17: https://opendata.cityofnewyork.us/overview/
  That page says the Open Data Law is Title 23, Chapter 5 of the New York City Administrative Code, in effect since 7 March 2012.

No API key is required for the SODA reads used here. `SOCRATA_APP_TOKEN` is optional and empty in `.env.example`. The committed capture did not send a token.

## Datasets

### 311 Service Requests from 2020 to Present

| | |
| --- | --- |
| Dataset id | `erm2-nwe9` |
| Page | https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9 |
| View metadata | https://data.cityofnewyork.us/api/views/erm2-nwe9.json |
| SODA | https://data.cityofnewyork.us/resource/erm2-nwe9.json |
| Agency on the page | 311, dataset owner NYC OpenData, agency field "Office of Technology and Innovation (OTI)" |
| Update | Daily. Page fetched 2026-10-17 said data last updated October 17, 2026 |
| Columns kept | `unique_key`, `created_date`, `agency`, `complaint_type`, `borough`, `community_board`, then `lat_rounded` / `lon_rounded` |
| Columns not stored | Address, street, cross streets, landmark, descriptor, resolution description, zip, raw `latitude` / `longitude` |

The public description says the dataset does not reveal the customer. It still has exact incident addresses. This lab does not request those fields and still rounds coordinates before writing the snapshot.

The 2010–2019 slice is a different dataset and is not used.

### NYPD Complaint Data Current (Year To Date)

| | |
| --- | --- |
| Dataset id | `5uac-w243` |
| Page | https://data.cityofnewyork.us/Public-Safety/NYPD-Complaint-Data-Current-Year-To-Date-/5uac-w243 |
| View metadata | https://data.cityofnewyork.us/api/views/5uac-w243.json |
| SODA | https://data.cityofnewyork.us/resource/5uac-w243.json |
| Attribution | Police Department (NYPD) |
| Columns kept | `cmplnt_num`, `cmplnt_fr_dt`, `law_cat_cd`, `ofns_desc`, `boro_nm`, then rounded coordinates |
| Columns not stored | Suspect and victim age, race, and sex; premise text; raw coordinates; internal descriptions |

The view description text still says "this year (2019)". That sentence is stale relative to the rows observed on 2026-10-17: a sample ordered by `cmplnt_fr_dt` was dated 2026-06-30, and view metadata `rowsUpdatedAt` was 2026-07-27T15:31:19Z. The committed snapshot uses the rows, not the year in that sentence.

### Fire Incident Dispatch Data (FDNY)

| | |
| --- | --- |
| Dataset id | `8m42-w767` |
| Page | https://data.cityofnewyork.us/Public-Safety/Fire-Incident-Dispatch-Data/8m42-w767 |
| View metadata | https://data.cityofnewyork.us/api/views/8m42-w767.json |
| SODA | https://data.cityofnewyork.us/resource/8m42-w767.json |
| Attribution | Fire Department of New York City (FDNY) |
| Columns kept | `starfire_incident_id`, `incident_datetime`, `incident_borough`, `communitydistrict`, `incident_classification`, `incident_classification_group`, `highest_alarm_level` |
| Columns not stored | `alarm_box_location` and every other column |

The City's description says specific locations are omitted and aggregated to protect information under HIPAA. This lab does not invent a point from the alarm box. The map may draw a schematic borough centroid and labels it `borough_centroid`. That centroid is not from the dataset. View metadata `rowsUpdatedAt` was 2026-10-05T14:02:19Z. The snapshot's newest `incident_datetime` values are 2026-09-30.

## Committed snapshots

Captured `2026-10-17T19:39:44.879483+00:00`.

Command:

```bash
EVENTS_OFFLINE=0 python3 -m events_briefing refresh-snapshots --online
```

| File | Rows |
| --- | --- |
| `fixtures/snapshots/erm2-nwe9.json` | 28 |
| `fixtures/snapshots/5uac-w243.json` | 20 |
| `fixtures/snapshots/8m42-w767.json` | 20 |
| `fixtures/snapshots/manifest.json` | capture note |

Pulls are listed inside each file. Coordinates in the 311 and NYPD files are already rounded to 2 decimal degrees. Raw latitude and longitude keys are not in the row objects. The word "latitude" appears only in the capture note and in `select_fields_requested`, which records what was asked of SODA before projection.

Floating timestamps are stored as the source sent them and interpreted as `America/New_York` at normalize time.

## Synthetic incidents

`src/events_briefing/evalkit/synthetic.py` is fictional. Those 10 rows are not from NYC Open Data. The eval gate uses them so a City data refresh cannot silently change the invariant result.
