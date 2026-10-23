"""Dataset pull specs. Select lists are the only columns requested from SODA."""

from __future__ import annotations

from dataclasses import dataclass

from events_briefing.models import SourceName


@dataclass(frozen=True)
class Pull:
    where: str
    order: str
    limit: int


@dataclass(frozen=True)
class DatasetSpec:
    source: SourceName
    dataset_id: str
    title: str
    page_url: str
    select_fields: tuple[str, ...]
    id_field: str
    pulls: tuple[Pull, ...]


DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        source="nyc_311",
        dataset_id="erm2-nwe9",
        title="311 Service Requests from 2020 to Present",
        page_url=(
            "https://data.cityofnewyork.us/Social-Services/"
            "311-Service-Requests-from-2020-to-Present/erm2-nwe9"
        ),
        select_fields=(
            "unique_key",
            "created_date",
            "agency",
            "complaint_type",
            "borough",
            "community_board",
            "latitude",
            "longitude",
        ),
        id_field="unique_key",
        pulls=(
            Pull(
                where="created_date > '2026-10-16T00:00:00' AND latitude IS NOT NULL",
                order="created_date DESC",
                limit=20,
            ),
            Pull(
                where=("complaint_type = 'Hazardous Materials' AND latitude IS NOT NULL"),
                order="created_date DESC",
                limit=4,
            ),
            Pull(
                where="complaint_type = 'Electrical' AND latitude IS NOT NULL",
                order="created_date DESC",
                limit=4,
            ),
        ),
    ),
    DatasetSpec(
        source="nypd_complaint",
        dataset_id="5uac-w243",
        title="NYPD Complaint Data Current (Year To Date)",
        page_url=(
            "https://data.cityofnewyork.us/Public-Safety/"
            "NYPD-Complaint-Data-Current-Year-To-Date-/5uac-w243"
        ),
        select_fields=(
            "cmplnt_num",
            "cmplnt_fr_dt",
            "law_cat_cd",
            "ofns_desc",
            "boro_nm",
            "latitude",
            "longitude",
        ),
        id_field="cmplnt_num",
        pulls=(
            Pull(
                where="latitude IS NOT NULL AND cmplnt_fr_dt IS NOT NULL",
                order="cmplnt_fr_dt DESC",
                limit=20,
            ),
        ),
    ),
    DatasetSpec(
        source="fdny_fire",
        dataset_id="8m42-w767",
        title="Fire Incident Dispatch Data",
        page_url=(
            "https://data.cityofnewyork.us/Public-Safety/Fire-Incident-Dispatch-Data/8m42-w767"
        ),
        select_fields=(
            "starfire_incident_id",
            "incident_datetime",
            "incident_borough",
            "communitydistrict",
            "incident_classification",
            "incident_classification_group",
            "highest_alarm_level",
        ),
        id_field="starfire_incident_id",
        pulls=(
            Pull(
                where="incident_datetime IS NOT NULL",
                order="incident_datetime DESC",
                limit=15,
            ),
            Pull(
                where="incident_classification_group = 'Structural Fires'",
                order="incident_datetime DESC",
                limit=6,
            ),
        ),
    ),
)


def dataset_by_id(dataset_id: str) -> DatasetSpec:
    for spec in DATASETS:
        if spec.dataset_id == dataset_id:
            return spec
    raise KeyError(dataset_id)
