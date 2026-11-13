RESEARCH_RUN_TO_COMPANY_STATUS = {
    "queued": "queued",
    "running": "running",
    "completed": "completed",
    "completed_with_errors": "partial",
    "partial": "partial",
    "failed": "failed",
}


def effective_research_status(company_status: str | None, latest_run_status: str | None) -> str:
    """Project persisted research state onto the shared company status values.

    Newer queued/running/terminal company states remain authoritative. For
    legacy rows left at the model's old default, the latest persisted run is
    the best available source of research completion state.
    """
    current = company_status or "not_started"
    if current in {"queued", "running", "partial", "completed", "failed"}:
        return current
    if latest_run_status in RESEARCH_RUN_TO_COMPANY_STATUS:
        return RESEARCH_RUN_TO_COMPANY_STATUS[latest_run_status]
    return "not_started" if current == "pending" else current
