"""Data: explores, their fields, and metric queries on the semantic layer."""

import asyncio
import uuid
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from lightdash_mcp.auth.provider import LightdashOAuthProvider
from lightdash_mcp.lightdash.client import LightdashClient
from lightdash_mcp.tools.common import READ, lightdash

Operator = Literal[
    "isNull", "notNull", "equals", "notEquals", "startsWith", "endsWith", "include", "doesNotInclude",
    "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual",
    "inThePast", "notInThePast", "inTheNext", "inTheCurrent", "notInTheCurrent", "inBetween", "notInBetween",
]

MAX_ROWS = 2500  # Lightdash's default largest results page
QUERY_TIMEOUT = 120


class Filter(BaseModel):
    field_id: str
    operator: Operator
    values: list[Any] = []
    settings: dict[str, Any] | None = None


class Sort(BaseModel):
    field_id: str
    descending: bool = False


def _field_id(field: dict[str, Any]) -> str:
    return f"{field['table']}_{field['name'].replace('.', '__')}"


def _fields(explore: dict[str, Any], kind: Literal["dimensions", "metrics"]) -> dict[str, dict[str, Any]]:
    return {
        _field_id(f): f
        for table in explore["tables"].values()
        for f in table[kind].values()
        if not f.get("hidden")
    }


def _summary(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "fieldId": _field_id(field),
        "label": field.get("label"),
        "type": field.get("type"),
        "table": field.get("tableLabel"),
        "description": field.get("description"),
    }


async def _explore(ld: LightdashClient, project_uuid: str, explore: str) -> dict[str, Any]:
    found = await ld.get(f"/api/v1/projects/{project_uuid}/explores/{explore}")
    if "tables" not in found:
        raise ToolError(f"Explore {explore} has errors: {found.get('errors')}")
    return found


def _filter_group(filters: list[Filter]) -> dict[str, Any] | None:
    if not filters:
        return None
    rules = [
        {"id": str(uuid.uuid4()), "target": {"fieldId": f.field_id}, "operator": f.operator, "values": f.values}
        | ({"settings": f.settings} if f.settings else {})
        for f in filters
    ]
    return {"id": str(uuid.uuid4()), "and": rules}


def register(server: MCPServer, provider: LightdashOAuthProvider) -> None:
    @server.tool(annotations=READ)
    async def list_explores(project_uuid: str) -> list[dict[str, Any]]:
        """List the explores of a project: the tables you can query, with what each one holds."""
        async with lightdash(provider) as ld:
            explores = await ld.get(f"/api/v1/projects/{project_uuid}/explores")
        return [
            {
                "name": e["name"],
                "label": e.get("label"),
                "group": e.get("groupLabel"),
                "description": e.get("description"),
                **({"errors": [error.get("message") for error in e["errors"]]} if e.get("errors") else {}),
            }
            for e in explores
        ]

    @server.tool(annotations=READ)
    async def get_explore(project_uuid: str, explore: str) -> dict[str, Any]:
        """List an explore's dimensions and metrics, joined tables included. Their field IDs go into run_query.
        Date dimensions come with one field per interval, such as orders_order_date_month."""
        async with lightdash(provider) as ld:
            found = await _explore(ld, project_uuid, explore)
        base = found["tables"][found["baseTable"]]
        return {
            "name": found["name"],
            "label": found.get("label"),
            "description": base.get("description"),
            "dimensions": [_summary(f) for f in _fields(found, "dimensions").values()],
            "metrics": [_summary(f) for f in _fields(found, "metrics").values()],
        }

    @server.tool(annotations=READ)
    async def run_query(
        project_uuid: str,
        explore: str,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        filters: list[Filter] | None = None,
        sorts: list[Sort] | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Query an explore by field ID: group by the dimensions, aggregate the metrics, all filters combined with AND.
        A filter on a metric applies after aggregation. Date filters such as inThePast take values [n] and
        settings {"unitOfTime": "days"}; inBetween takes two values. Returns up to `limit` rows, at most 2500."""
        dimensions, metrics, filters, sorts = dimensions or [], metrics or [], filters or [], sorts or []
        if not dimensions and not metrics:
            raise ToolError("Give at least one dimension or metric.")
        async with lightdash(provider) as ld:
            found = await _explore(ld, project_uuid, explore)
            known_dimensions, known_metrics = _fields(found, "dimensions"), _fields(found, "metrics")
            unknown = [
                f
                for f in [*dimensions, *metrics, *(f.field_id for f in filters), *(s.field_id for s in sorts)]
                if f not in known_dimensions and f not in known_metrics
            ]
            if unknown:
                raise ToolError(f"Unknown fields in {explore}: {', '.join(unknown)}. See get_explore.")
            query = {
                "exploreName": explore,
                "dimensions": dimensions,
                "metrics": metrics,
                "filters": {
                    key: group
                    for key, group in (
                        ("dimensions", _filter_group([f for f in filters if f.field_id in known_dimensions])),
                        ("metrics", _filter_group([f for f in filters if f.field_id in known_metrics])),
                    )
                    if group
                },
                "sorts": [{"fieldId": s.field_id, "descending": s.descending} for s in sorts],
                "limit": max(1, min(limit, MAX_ROWS)),
                "tableCalculations": [],
            }
            started = await ld.request(
                "POST", f"/api/v2/projects/{project_uuid}/query/metric-query", json={"query": query, "context": "api"}
            )
            path = f"/api/v2/projects/{project_uuid}/query/{started['queryUuid']}"
            for _ in range(QUERY_TIMEOUT * 2):
                results = await ld.get(path, pageSize=query["limit"])
                if results["status"] not in ("pending", "queued", "executing"):
                    break
                await asyncio.sleep(0.5)
            else:
                await ld.request("POST", f"{path}/cancel")
                raise ToolError(f"The query took more than {QUERY_TIMEOUT} seconds and was cancelled.")
        if results["status"] != "ready":
            raise ToolError(f"The query failed ({results['status']}): {results.get('error')}")
        return {
            "columns": {fid: column.get("label") for fid, column in results["columns"].items()},
            "rows": [{fid: cell["value"]["raw"] for fid, cell in row.items()} for row in results["rows"]],
        }
