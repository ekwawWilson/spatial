import shutil
import traceback
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.tenancy import tenant_context

from . import gdal_io, osm
from .exporter import run_export
from .importer import ImportAborted, run_import, set_progress
from .models import DataJob


def job_dir(job: DataJob) -> Path:
    return Path(settings.MEDIA_ROOT) / "transfer" / str(job.uuid)


def source_file(job: DataJob) -> Path:
    return job_dir(job) / "source" / job.original_name


@shared_task  # type: ignore[misc]
def run_job(job_id: int, district_id: int, user_id: int | None) -> None:
    """Runs an import or export as the job's owner, in the job's district."""
    with tenant_context(district_id, user_id=user_id):
        job = DataJob.objects.select_related("project").get(pk=job_id)
        job.status = DataJob.Status.RUNNING
        job.save(update_fields=["status"])
    try:
        with tenant_context(district_id, user_id=user_id):
            job = DataJob.objects.select_related("project").get(pk=job_id)
            if job.kind == DataJob.Kind.IMPORT:
                report = run_import(job, source_file(job))
                result_name = ""
            else:
                out = job_dir(job) / "result"
                if out.exists():
                    shutil.rmtree(out)
                out.mkdir(parents=True)
                archive, report = run_export(job, out)
                result_name = archive.name
            job.report = report
            job.result_name = result_name
            job.status = DataJob.Status.DONE
            job.finished_at = timezone.now()
            job.save(update_fields=["report", "result_name", "status", "finished_at"])
    except (ValidationError, ImportAborted) as exc:
        _fail(job_id, district_id, user_id, "; ".join(getattr(exc, "messages", [str(exc)])))
    except Exception as exc:  # noqa: BLE001 - record any failure on the job
        _fail(
            job_id,
            district_id,
            user_id,
            f"Unexpected error: {exc}\n{traceback.format_exc(limit=3)}",
        )


def _fail(job_id: int, district_id: int, user_id: int | None, message: str) -> None:
    with tenant_context(district_id, user_id=user_id):
        job = DataJob.objects.get(pk=job_id)
        job.status = DataJob.Status.FAILED
        job.error = message
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        set_progress(job, 0, 0, "Failed")


@shared_task  # type: ignore[misc]
def run_osm(job_id: int, district_id: int, user_id: int | None) -> None:
    """Brings OpenStreetMap features inside the job's area into the project:
    asks OpenStreetMap (outside any database transaction: it can take a
    minute), then imports what came back like an uploaded GeoPackage."""
    try:
        with tenant_context(district_id, user_id=user_id):
            job = DataJob.objects.get(pk=job_id)
            job.status = DataJob.Status.RUNNING
            job.save(update_fields=["status"])
            set_progress(job, 0, 0, "Asking OpenStreetMap")
            request = job.plan["osm"]
        kinds = [osm.KIND_BY_CODE[code] for code in request["kinds"]]
        data = osm.fetch(osm.query(kinds, request["area"]))
        with tenant_context(district_id, user_id=user_id):
            job = DataJob.objects.select_related("project", "project__crs", "created_by").get(
                pk=job_id
            )
            layers = {k.code: osm.target_layer(job.project, k, job.created_by) for k in kinds}
            skip = {code: osm.existing_ids(layer) for code, layer in layers.items()}
            file = source_file(job)
            counts = osm.write_geopackage(data, kinds, request["area"], skip, file)
            job.inspection = gdal_io.inspect(file, "gpkg")
            job.plan = {
                **job.plan,
                "layers": [
                    {
                        "source": kind.code,
                        "target_layer": layers[kind.code].pk,
                        "crs": "EPSG:4326",
                        "crs_confirmed": True,
                        "fields": [
                            {"source": name, "target": name}
                            for name in (*osm.FIELD_NAMES, *(f for f, _ in kind.fields))
                        ],
                        "invalid_geometry": "fix",
                    }
                    for kind in kinds
                    if counts[kind.code]
                ],
            }
            job.save(update_fields=["inspection", "plan"])
            report = run_import(job, file) if job.plan["layers"] else {"layers": []}
            set_progress(job, 1, 1, "Done")
            report["osm"] = {
                "found": counts,
                "already_in_project": {code: len(ids) for code, ids in skip.items()},
                "layers": {code: layer.pk for code, layer in layers.items()},
                "attribution": osm.ATTRIBUTION,
            }
            job.report = report
            job.status = DataJob.Status.DONE
            job.finished_at = timezone.now()
            job.save(update_fields=["report", "status", "finished_at"])
    except (ValidationError, ImportAborted) as exc:
        _fail(job_id, district_id, user_id, "; ".join(getattr(exc, "messages", [str(exc)])))
    except Exception as exc:  # noqa: BLE001 - record any failure on the job
        _fail(
            job_id,
            district_id,
            user_id,
            f"Unexpected error: {exc}\n{traceback.format_exc(limit=3)}",
        )
