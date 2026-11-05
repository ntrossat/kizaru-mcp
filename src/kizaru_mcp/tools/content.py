"""Content: finding charts and dashboards, reading dashboards, unused content, validation errors, moving and deleting."""

import asyncio
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from kizaru_mcp.auth.provider import LightdashOAuthProvider
from kizaru_mcp.lightdash import LightdashClient
from kizaru_mcp.tools.common import DESTRUCTIVE, READ, WRITE, Uuid, lightdash

ContentType = Literal["chart", "dashboard", "space"]

PAGE_SIZE = 100
VALIDATION_TIMEOUT = 120


async def _content(ld: LightdashClient, project_uuid: str, **params: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in count(1):
        results = await ld.get("/api/v2/content", projectUuids=project_uuid, pageSize=PAGE_SIZE, page=page, **params)
        items += results["data"]
        if page >= results["pagination"]["totalPageCount"]:
            return items


async def _item(ld: LightdashClient, project_uuid: str, content_type: ContentType, uuid: str) -> dict[str, Any]:
    items = await _content(ld, project_uuid, uuids=uuid, contentTypes=content_type)
    if not items:
        raise ToolError(f"No {content_type} {uuid} in this project.")
    return items[0]


def _payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = {"contentType": item["contentType"], "uuid": item["uuid"]}
    if item["contentType"] == "chart":
        payload["source"] = item["source"]
    return payload


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "contentType": item["contentType"],
        "uuid": item["uuid"],
        "name": item["name"],
        "space": (item.get("space") or {}).get("name"),
    }


def _tile(tile: dict[str, Any], tabs: dict[str, str]) -> dict[str, Any]:
    properties = tile["properties"]
    summary = {"type": tile["type"], "title": properties.get("title") or properties.get("chartName")}
    if tabs:
        summary["tab"] = tabs.get(tile.get("tabUuid"))
    if tile["type"] == "saved_chart":
        summary |= {"chartUuid": properties.get("savedChartUuid"), "chartKind": properties.get("lastVersionChartKind")}
    elif tile["type"] == "markdown":
        summary["content"] = properties.get("content")
    return summary


def register(server: MCPServer, provider: LightdashOAuthProvider) -> None:
    @server.tool(annotations=READ)
    async def search_content(
        project_uuid: Uuid, search: str | None = None, content_type: Literal["chart", "dashboard"] | None = None
    ) -> list[dict[str, Any]]:
        """Find charts and dashboards by name, or list them all without search.
        Run a chart with run_chart, and open a dashboard with get_dashboard."""
        async with lightdash(provider) as ld:
            items = await _content(ld, project_uuid, search=search, contentTypes=content_type or ["chart", "dashboard"])
        return [
            {**_summary(i), "description": i.get("description"), "views": i.get("views"), "lastUpdatedAt": i.get("lastUpdatedAt")}
            for i in items
        ]

    @server.tool(annotations=READ)
    async def get_dashboard(dashboard_uuid: Uuid) -> dict[str, Any]:
        """Show a dashboard's filters and tiles in layout order: its charts, to run with run_chart and the
        dashboard's UUID, and its text."""
        async with lightdash(provider) as ld:
            dashboard = await ld.get(f"/api/v1/dashboards/{dashboard_uuid}")
        tabs = sorted(dashboard.get("tabs") or [], key=lambda t: t["order"])
        names, order = {t["uuid"]: t["name"] for t in tabs}, {t["uuid"]: n for n, t in enumerate(tabs)}
        tiles = sorted(dashboard["tiles"], key=lambda t: (order.get(t.get("tabUuid"), 0), t["y"], t["x"]))
        filters = dashboard.get("filters") or {}
        return {
            "name": dashboard["name"],
            "description": dashboard.get("description"),
            "projectUuid": dashboard["projectUuid"],
            "space": dashboard.get("spaceName"),
            "filters": [
                {
                    "fieldId": f["target"]["fieldId"],
                    "operator": f["operator"],
                    "values": f.get("values"),
                    "disabled": f.get("disabled", False),
                }
                for f in [*filters.get("dimensions", []), *filters.get("metrics", [])]
            ],
            "tiles": [_tile(t, names) for t in tiles],
        }

    @server.tool(annotations=READ)
    async def find_unused_content(
        project_uuid: Uuid, unused_days: int = 90, content_type: Literal["chart", "dashboard"] | None = None
    ) -> list[dict[str, Any]]:
        """Find charts and dashboards nobody has viewed in `unused_days` days, never-viewed first.
        Content created within that window is left out."""
        cutoff = datetime.now(UTC) - timedelta(days=unused_days)
        async with lightdash(provider) as ld:
            items = await _content(ld, project_uuid, contentTypes=content_type or ["chart", "dashboard"])

        def before_cutoff(value: str | None) -> bool:
            return value is None or datetime.fromisoformat(value) < cutoff

        unused = [i for i in items if before_cutoff(i.get("lastViewedAt")) and before_cutoff(i["createdAt"])]
        unused.sort(key=lambda i: (i.get("lastViewedAt") is not None, i.get("lastViewedAt") or "", i["createdAt"]))
        return [
            {
                **_summary(i),
                "views": i.get("views"),
                "lastViewedAt": i.get("lastViewedAt"),
                "createdAt": i["createdAt"],
                "lastUpdatedAt": i.get("lastUpdatedAt"),
            }
            for i in unused
        ]

    @server.tool(annotations=READ)
    async def list_validation_errors(project_uuid: Uuid, revalidate: bool = False) -> list[dict[str, Any]]:
        """List broken charts and dashboards: fields that no longer exist, bad configurations.
        Results come from the last validation run; set revalidate to run a fresh one first."""
        async with lightdash(provider) as ld:
            if revalidate:
                job = await ld.request("POST", f"/api/v1/projects/{project_uuid}/validate")
                for _ in range(VALIDATION_TIMEOUT):
                    status = (await ld.get(f"/api/v1/schedulers/job/{job['jobId']}/status"))["status"]
                    if status in ("completed", "error"):
                        break
                    await asyncio.sleep(1)
                if status != "completed":
                    raise ToolError(f"Validation did not complete (status: {status}).")
            errors = await ld.get(f"/api/v1/projects/{project_uuid}/validate")
        return [
            {
                "source": e.get("source"),
                "name": e.get("name"),
                "uuid": e.get("chartUuid") or e.get("dashboardUuid") or e.get("tableName"),
                "errorType": e.get("errorType"),
                "error": e.get("error"),
                "fieldName": e.get("fieldName"),
                "views": e.get("chartViews", e.get("dashboardViews")),
                "lastUpdatedBy": e.get("lastUpdatedBy"),
            }
            for e in errors
        ]

    @server.tool(annotations=WRITE)
    async def move_content(project_uuid: Uuid, content_type: ContentType, uuid: Uuid, target_space_uuid: Uuid) -> str:
        """Move a chart, dashboard or space into another space."""
        async with lightdash(provider) as ld:
            item = await _item(ld, project_uuid, content_type, uuid)
            await ld.request(
                "POST",
                f"/api/v2/content/{project_uuid}/move",
                json={"item": _payload(item), "action": {"type": "move", "targetSpaceUuid": target_space_uuid}},
            )
        return f'Moved {content_type} "{item["name"]}".'

    @server.tool(annotations=DESTRUCTIVE)
    async def delete_content(project_uuid: Uuid, content_type: ContentType, uuid: Uuid, dry_run: bool = True) -> dict[str, Any]:
        """Delete a chart, dashboard or space. A space is deleted with everything in it.
        dry_run, on by default, shows what would be deleted. Pass dry_run=false to delete."""
        async with lightdash(provider) as ld:
            item = await _item(ld, project_uuid, content_type, uuid)
            impact: dict[str, Any] = {"item": _summary(item)}
            if content_type == "space":
                found = await ld.get(f"/api/v1/projects/{project_uuid}/spaces/{uuid}/delete-impact")
                impact["includes"] = {k: [c.get("name") for c in v] for k, v in found.items() if isinstance(v, list) and v}
            if dry_run:
                return {"wouldDelete": impact}
            await ld.request(
                "POST", f"/api/v2/content/{project_uuid}/delete", json={"item": _payload(item), "action": {"type": "delete"}}
            )
        return {"deleted": impact}
