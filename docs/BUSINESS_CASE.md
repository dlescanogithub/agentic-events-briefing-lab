# Business case

Fictional desk only. Editorial Muelle is a name used in these docs for a made-up civic newsroom.

## Problem

A morning briefing desk reading public NYC incident feeds sees a lot of noise complaints and a smaller set of life-safety items (fires, assaults, hazardous materials). Volume alone is a bad sort. A second failure mode is a draft that reads as if it had already been sent.

## What this repo shows

An explicit rubric keeps life-safety items above noise on a synthetic labeled set. A state machine blocks a local publish until approval. The default path costs 0 USD and does not call a vendor.

Measured 2026-10-17, package 0.1.0, Python 3.12.3, command `python3 -m events_briefing eval`: 8/8 scenarios PASS, n=10, life-safety-above-noise rate 1.0. That number is the lab gate, not a business KPI from a newsroom.

## ROI model [EST]

Assumptions, all illustrative:

- A person scans on the order of 30 items in a morning sitting. **[EST]**
- A ranked draft might avoid about 20 minutes of that sitting. **[EST]**. Not measured here.
- An illustrative loaded cost of 45 USD/hour. **[EST]**. Not a wage, not a quote, not a fee.
- 20/60 * 45 = 15 USD per morning. **[EST]**
- 15 USD * 20 mornings = 300 USD per month. **[EST]**

This repository does not measure time saved, does not charge a fee, and does not include City data terms in that arithmetic. If the assumption of 20 minutes is wrong, the estimate is wrong.

## What would have to be true

- The desk agrees the rubric floors match their definition of life-safety.
- A human still approves. The model does not.
- "Publish" stays a local file until an authenticated channel exists. That channel is not in this repo.
