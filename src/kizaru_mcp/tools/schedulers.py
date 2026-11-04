"""Scheduled deliveries: list, pause, edit and delete."""

from typing import Any

from mcp.server.mcpserver import MCPServer

from kizaru_mcp.auth.provider import LightdashOAuthProvider
from kizaru_mcp.tools.common import DESTRUCTIVE, READ, WRITE, Uuid, data, lightdash

# Fields Lightdash expects back when a scheduler is updated: PATCH takes the whole scheduler.
UPDATABLE = (
    "name",
    "message",
    "format",
    "cron",
    "timezone",
    "options",
    "targets",
    "includeLinks",
    "enabled",
    "thresholds",
    "notificationFrequency",
    "plainTextEmail",
)


def _summary(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "schedulerUuid": s["schedulerUuid"],
        "name": s["name"],
        "enabled": s.get("enabled"),
        "cron": s.get("cron"),
        "timezone": s.get("timezone"),
        "format": s.get("format"),
        "content": s.get("savedChartName") or s.get("dashboardName") or s.get("savedSqlName") or s.get("appName"),
        "owner": s.get("createdByName"),
        "recipients": [t.get("recipient") or t.get("channel") or t.get("url") for t in s.get("targets") or []],
        "latestRun": s.get("latestRun"),
    }


def register(server: MCPServer, provider: LightdashOAuthProvider) -> None:
    @server.tool(annotations=READ)
    async def list_schedulers(project_uuid: Uuid, search: str | None = None) -> list[dict[str, Any]]:
        """List a project's scheduled deliveries with their schedule, owner, recipients and latest run."""
        async with lightdash(provider) as ld:
            schedulers = data(
                await ld.get(f"/api/v1/schedulers/{project_uuid}/list", searchQuery=search, includeLatestRun="true")
            )
        return [_summary(s) for s in schedulers]

    @server.tool(annotations=WRITE)
    async def set_scheduler_enabled(scheduler_uuid: Uuid, enabled: bool) -> str:
        """Pause (enabled=false) or resume (enabled=true) a scheduled delivery."""
        async with lightdash(provider) as ld:
            await ld.request("PATCH", f"/api/v1/schedulers/{scheduler_uuid}/enabled", json={"enabled": enabled})
        return "Resumed the delivery." if enabled else "Paused the delivery."

    @server.tool(annotations=WRITE)
    async def update_scheduler(
        scheduler_uuid: Uuid,
        name: str | None = None,
        cron: str | None = None,
        timezone: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Change a scheduled delivery's name, schedule (cron expression), timezone or message.
        Fields left out stay as they are."""
        changes = {
            k: v for k, v in {"name": name, "cron": cron, "timezone": timezone, "message": message}.items() if v is not None
        }
        async with lightdash(provider) as ld:
            current = await ld.get(f"/api/v1/schedulers/{scheduler_uuid}")
            body = {k: current[k] for k in UPDATABLE if k in current} | changes
            updated = await ld.request("PATCH", f"/api/v1/schedulers/{scheduler_uuid}", json=body)
        return _summary(updated)

    @server.tool(annotations=DESTRUCTIVE)
    async def delete_scheduler(scheduler_uuid: Uuid, dry_run: bool = True) -> dict[str, Any]:
        """Delete a scheduled delivery. dry_run, on by default, shows it. Pass dry_run=false to delete it."""
        async with lightdash(provider) as ld:
            scheduler = _summary(await ld.get(f"/api/v1/schedulers/{scheduler_uuid}"))
            if dry_run:
                return {"wouldDelete": scheduler}
            await ld.request("DELETE", f"/api/v1/schedulers/{scheduler_uuid}")
        return {"deleted": scheduler}
