import shutil
import traceback
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.tenancy import tenant_context

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
