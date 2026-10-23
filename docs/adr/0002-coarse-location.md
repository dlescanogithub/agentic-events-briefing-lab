# ADR 0002: Coarse location, no free text

## Status

Accepted

## Context

311 rows can carry an exact address even when the customer is not named. NYPD rows can carry victim and suspect fields. FDNY already drops points and still has an alarm-box location string.

## Decision

Request an allowlist. Round latitude and longitude to 2 decimal degrees before the snapshot is written (about 1.1 km). Compute geohash precision 6 only from those rounded numbers (about 1.2 km by 0.6 km). Drop addresses, names, phones, descriptors, and demographic fields. For FDNY, do not invent a source point; a schematic borough centroid is labeled `borough_centroid` and does not count toward density.

## Consequences

Maps are coarse on purpose. A test fails if a forbidden key is in a snapshot or in a normalized dump. Two decimal degrees can still feel precise in a dense city; a stricter desk should drop coordinates rather than add a third decimal.
