"""Every tool against the local Lightdash, as the admin and as the viewer."""

from typing import Any

import httpx
import pytest

EDITOR = "demo2@lightdash.com"


def ok(result) -> Any:
    assert not result.is_error, result.content
    content = result.structured_content
    return content["result"] if set(content) == {"result"} else content


def denied(result) -> str:
    assert result.is_error
    return result.content[0].text


@pytest.fixture
def editor_uuid(lightdash_admin: httpx.Client) -> str:
    users = lightdash_admin.get("/api/v1/org/users").json()["results"]["data"]
    return next(u["userUuid"] for u in users if u["email"] == EDITOR)


@pytest.fixture
def space(lightdash_admin: httpx.Client, project_uuid: str):
    created = lightdash_admin.post(f"/api/v1/projects/{project_uuid}/spaces", json={"name": "mcp test space"})
    uuid = created.json()["results"]["uuid"]
    yield uuid
    lightdash_admin.delete(f"/api/v1/projects/{project_uuid}/spaces/{uuid}")


@pytest.fixture
def scheduler(lightdash_admin: httpx.Client, project_uuid: str):
    charts = lightdash_admin.get(
        "/api/v2/content", params={"projectUuids": project_uuid, "contentTypes": "chart", "pageSize": 100}
    ).json()["results"]["data"]
    chart = next(c for c in charts if c["chartKind"] in ("vertical_bar", "line", "table"))
    created = lightdash_admin.post(
        f"/api/v1/saved/{chart['uuid']}/schedulers",
        json={
            "name": "mcp test delivery",
            "message": "",
            "format": "csv",
            "cron": "0 9 * * 1",
            "timezone": "UTC",
            "enabled": True,
            "options": {"formatted": True, "limit": "table"},
            "targets": [{"recipient": "demo@lightdash.com"}],
            "includeLinks": True,
            "appUuid": None,  # required by the request schema, though not for a chart
            "appName": None,
        },
    )
    uuid = created.json()["results"]["schedulerUuid"]
    yield uuid
    lightdash_admin.delete(f"/api/v1/schedulers/{uuid}")


async def test_read_tools(admin, tool, project_uuid):
    projects = ok(await tool(admin, "list_projects"))
    assert project_uuid in [p["projectUuid"] for p in projects]

    users = ok(await tool(admin, "list_users"))
    assert {"demo@lightdash.com", EDITOR} <= {u["email"] for u in users}

    groups = ok(await tool(admin, "list_groups"))
    assert groups and all("members" in g for g in groups)

    roles = ok(await tool(admin, "list_roles"))
    assert {"Admin", "Viewer"} <= {r["name"] for r in roles}

    access = ok(await tool(admin, "list_project_access", {"project_uuid": project_uuid}))
    assert any(u["email"] == "demo@lightdash.com" and u["projectRole"] == "admin" for u in access["users"])

    spaces = ok(await tool(admin, "list_spaces", {"project_uuid": project_uuid}))
    assert spaces
    space_access = ok(
        await tool(admin, "list_space_access", {"project_uuid": project_uuid, "space_uuid": spaces[0]["spaceUuid"]})
    )
    assert space_access["users"]

    unused = ok(await tool(admin, "find_unused_content", {"project_uuid": project_uuid, "unused_days": 0}))
    assert unused and {u["contentType"] for u in unused} <= {"chart", "dashboard"}

    errors = ok(await tool(admin, "list_validation_errors", {"project_uuid": project_uuid, "revalidate": True}))
    assert isinstance(errors, list)


async def test_permissions_follow_the_user(admin, viewer, tool, project_uuid, editor_uuid):
    assert ok(await tool(admin, "list_roles"))
    assert "Permission denied" in denied(await tool(viewer, "list_roles"))
    assert "Permission denied" in denied(await tool(viewer, "list_schedulers", {"project_uuid": project_uuid}))
    message = denied(
        await tool(viewer, "grant_project_access", {"project_uuid": project_uuid, "email": EDITOR, "role": "viewer"})
    )
    assert "Permission denied" in message


async def test_project_access_lifecycle(admin, tool, lightdash_admin, project_uuid, editor_uuid):
    lightdash_admin.delete(f"/api/v1/projects/{project_uuid}/access/{editor_uuid}")
    args = {"project_uuid": project_uuid}

    def direct_role(access) -> str | None:
        return next(u["directRole"] for u in access["users"] if u["userUuid"] == editor_uuid)

    ok(await tool(admin, "grant_project_access", {**args, "email": EDITOR, "role": "editor"}))
    assert direct_role(ok(await tool(admin, "list_project_access", args))) == "editor"

    ok(await tool(admin, "update_project_access", {**args, "user_uuid": editor_uuid, "role": "viewer"}))
    assert direct_role(ok(await tool(admin, "list_project_access", args))) == "viewer"

    preview = ok(await tool(admin, "revoke_project_access", {**args, "user_uuid": editor_uuid}))
    assert preview["wouldRemove"]["role"] == "viewer"
    assert direct_role(ok(await tool(admin, "list_project_access", args))) == "viewer"

    ok(await tool(admin, "revoke_project_access", {**args, "user_uuid": editor_uuid, "dry_run": False}))
    assert direct_role(ok(await tool(admin, "list_project_access", args))) is None


async def test_group_membership(admin, tool, editor_uuid):
    group = next(g for g in ok(await tool(admin, "list_groups")) if g["name"] == "Org 1 Group")
    args = {"group_uuid": group["groupUuid"], "user_uuid": editor_uuid}

    def members() -> set[str]:
        return {m["userUuid"] for m in next(g for g in groups if g["groupUuid"] == group["groupUuid"])["members"]}

    ok(await tool(admin, "add_group_member", args))
    ok(await tool(admin, "add_group_member", args))  # idempotent
    groups = ok(await tool(admin, "list_groups"))
    assert editor_uuid in members()

    assert ok(await tool(admin, "remove_group_member", args))["wouldRemove"]["email"] == EDITOR
    ok(await tool(admin, "remove_group_member", {**args, "dry_run": False}))
    groups = ok(await tool(admin, "list_groups"))
    assert editor_uuid not in members()


async def test_scheduler_lifecycle(admin, tool, project_uuid, scheduler, lightdash_admin):
    def find(schedulers) -> dict[str, Any]:
        return next(s for s in schedulers if s["schedulerUuid"] == scheduler)

    listed = find(ok(await tool(admin, "list_schedulers", {"project_uuid": project_uuid})))
    assert listed["recipients"] == ["demo@lightdash.com"]

    updated = ok(await tool(admin, "update_scheduler", {"scheduler_uuid": scheduler, "name": "renamed", "cron": "0 7 * * 2"}))
    assert (updated["name"], updated["cron"], updated["recipients"]) == ("renamed", "0 7 * * 2", ["demo@lightdash.com"])

    ok(await tool(admin, "set_scheduler_enabled", {"scheduler_uuid": scheduler, "enabled": False}))
    assert find(ok(await tool(admin, "list_schedulers", {"project_uuid": project_uuid})))["enabled"] is False

    assert ok(await tool(admin, "delete_scheduler", {"scheduler_uuid": scheduler}))["wouldDelete"]["name"] == "renamed"
    assert lightdash_admin.get(f"/api/v1/schedulers/{scheduler}").status_code == 200
    ok(await tool(admin, "delete_scheduler", {"scheduler_uuid": scheduler, "dry_run": False}))
    assert lightdash_admin.get(f"/api/v1/schedulers/{scheduler}").status_code == 404


async def test_move_and_delete_content(admin, tool, project_uuid, space, lightdash_admin):
    charts = lightdash_admin.get(
        "/api/v2/content", params={"projectUuids": project_uuid, "contentTypes": "chart", "pageSize": 1}
    ).json()["results"]["data"]
    chart, home = charts[0]["uuid"], charts[0]["space"]["uuid"]

    def chart_space() -> str:
        return lightdash_admin.get("/api/v2/content", params={"projectUuids": project_uuid, "uuids": chart}).json()["results"][
            "data"
        ][0]["space"]["uuid"]

    move = {"project_uuid": project_uuid, "content_type": "chart", "uuid": chart}
    ok(await tool(admin, "move_content", {**move, "target_space_uuid": space}))
    assert chart_space() == space
    ok(await tool(admin, "move_content", {**move, "target_space_uuid": home}))
    assert chart_space() == home

    delete = {"project_uuid": project_uuid, "content_type": "space", "uuid": space}
    preview = ok(await tool(admin, "delete_content", delete))
    assert preview["wouldDelete"]["item"]["name"] == "mcp test space"
    ok(await tool(admin, "delete_content", {**delete, "dry_run": False}))
    spaces = ok(await tool(admin, "list_spaces", {"project_uuid": project_uuid}))
    assert space not in [s["spaceUuid"] for s in spaces]


async def test_data_tools(admin, viewer, tool, project_uuid):
    args = {"project_uuid": project_uuid}
    assert "orders" in [e["name"] for e in ok(await tool(viewer, "list_explores", args))]

    explore = ok(await tool(viewer, "get_explore", {**args, "explore": "orders"}))
    assert "orders_status" in [d["fieldId"] for d in explore["dimensions"]]
    assert "customers_first_name" in [d["fieldId"] for d in explore["dimensions"]]  # joined table
    assert "orders_total_order_amount" in [m["fieldId"] for m in explore["metrics"]]

    query = {
        **args,
        "explore": "orders",
        "dimensions": ["orders_status"],
        "metrics": ["orders_unique_order_count"],
        "filters": [
            {"field_id": "orders_status", "operator": "notEquals", "values": ["returned"]},
            {"field_id": "orders_unique_order_count", "operator": "greaterThan", "values": [0]},
        ],
        "sorts": [{"field_id": "orders_unique_order_count", "descending": True}],
        "limit": 3,
    }
    result = ok(await tool(admin, "run_query", query))
    assert set(result["columns"]) == {"orders_status", "orders_unique_order_count"}
    counts = [int(r["orders_unique_order_count"]) for r in result["rows"]]  # bigint counts come as strings
    assert 0 < len(counts) <= 3 and counts == sorted(counts, reverse=True) and all(c > 0 for c in counts)
    assert "returned" not in [r["orders_status"] for r in result["rows"]]

    assert "Permission denied" in denied(await tool(viewer, "run_query", query))  # viewers only see saved charts
    unknown = denied(await tool(admin, "run_query", {**args, "explore": "orders", "metrics": ["orders_nope"]}))
    assert "Unknown fields in orders: orders_nope" in unknown
