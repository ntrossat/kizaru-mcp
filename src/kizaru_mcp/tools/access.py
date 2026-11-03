"""Who can see what: users, groups, roles, project access and space access."""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from kizaru_mcp.auth.provider import LightdashOAuthProvider
from kizaru_mcp.tools.common import CREATE, DESTRUCTIVE, READ, WRITE, Uuid, data, full_name, lightdash, pick

ProjectRole = Literal["viewer", "interactive_viewer", "editor", "developer", "admin"]


def register(server: MCPServer, provider: LightdashOAuthProvider) -> None:
    @server.tool(annotations=READ)
    async def list_projects() -> list[dict[str, Any]]:
        """List the Lightdash projects you can see. Most tools need a project UUID from here."""
        async with lightdash(provider) as ld:
            return [pick(p, "projectUuid", "name", "type") for p in await ld.get("/api/v1/org/projects")]

    @server.tool(annotations=READ)
    async def list_users(search: str | None = None) -> list[dict[str, Any]]:
        """List organization members with their organization role, status and groups."""
        async with lightdash(provider) as ld:
            users = data(await ld.get("/api/v1/org/users", searchQuery=search, includeGroups=100))
        return [
            {
                "userUuid": u["userUuid"],
                "name": full_name(u),
                "email": u.get("email"),
                "organizationRole": u.get("role"),
                "isActive": u.get("isActive"),
                "isPending": u.get("isPending"),
                "groups": [g["name"] for g in u.get("groups") or []],
            }
            for u in users
        ]

    @server.tool(annotations=READ)
    async def list_groups(search: str | None = None) -> list[dict[str, Any]]:
        """List groups and their members."""
        async with lightdash(provider) as ld:
            groups = data(await ld.get("/api/v1/org/groups", searchQuery=search, includeMembers=1000))
        return [
            {
                "groupUuid": g["uuid"],
                "name": g["name"],
                "members": [
                    {"userUuid": m["userUuid"], "name": full_name(m), "email": m.get("email")} for m in g.get("members") or []
                ],
            }
            for g in groups
        ]

    @server.tool(annotations=READ)
    async def list_roles() -> list[dict[str, Any]]:
        """List the organization's roles, system and custom, with the permission scopes each grants."""
        async with lightdash(provider) as ld:
            org = await ld.get("/api/v1/org")
            roles = await ld.get(f"/api/v2/orgs/{org['organizationUuid']}/roles")
        return [pick(r, "roleUuid", "name", "description", "ownerType", "level", "scopes") for r in roles]

    @server.tool(annotations=READ)
    async def list_project_access(project_uuid: Uuid) -> dict[str, Any]:
        """Show who can access a project: each user's effective role (from their organization role,
        a direct grant or a group), their direct grant if any, and the groups with access."""
        async with lightdash(provider) as ld:
            users = data(await ld.get("/api/v1/org/users", projectUuid=project_uuid, includeGroups=100))
            direct = {m["userUuid"]: m["role"] for m in await ld.get(f"/api/v1/projects/{project_uuid}/access")}
            group_access = await ld.get(f"/api/v1/projects/{project_uuid}/groupAccesses")
            group_names = {g["uuid"]: g["name"] for g in data(await ld.get("/api/v1/org/groups"))} if group_access else {}
        return {
            "users": [
                {
                    "userUuid": u["userUuid"],
                    "name": full_name(u),
                    "email": u.get("email"),
                    "projectRole": u.get("role"),
                    "directRole": direct.get(u["userUuid"]),
                    "groups": [g["name"] for g in u.get("groups") or []],
                }
                for u in users
            ],
            "groups": [
                {"groupUuid": g["groupUuid"], "name": group_names.get(g["groupUuid"]), "projectRole": g["role"]}
                for g in group_access
            ],
        }

    @server.tool(annotations=READ)
    async def list_spaces(project_uuid: Uuid) -> list[dict[str, Any]]:
        """List a project's spaces, nested ones included, with their content counts."""
        async with lightdash(provider) as ld:
            spaces = await ld.get(f"/api/v1/projects/{project_uuid}/spaces")
        return [
            {
                "spaceUuid": s["uuid"],
                "name": s["name"],
                "parentSpaceUuid": s.get("parentSpaceUuid"),
                "inheritsParentPermissions": s.get("inheritParentPermissions"),
                "charts": int(s.get("chartCount") or 0),
                "dashboards": int(s.get("dashboardCount") or 0),
                "childSpaces": int(s.get("childSpaceCount") or 0),
            }
            for s in spaces
        ]

    @server.tool(annotations=READ)
    async def list_space_access(project_uuid: Uuid, space_uuid: Uuid) -> dict[str, Any]:
        """Show who can access a space and why: direct access, or inherited from the organization,
        the project or a parent space."""
        async with lightdash(provider) as ld:
            space = await ld.get(f"/api/v1/projects/{project_uuid}/spaces/{space_uuid}")
        return {
            "space": space["name"],
            "inheritsParentPermissions": space.get("inheritParentPermissions"),
            "users": [
                {
                    "userUuid": a["userUuid"],
                    "name": full_name(a),
                    "email": a.get("email"),
                    "spaceRole": a.get("role"),
                    "hasDirectAccess": a.get("hasDirectAccess"),
                    "inheritedFrom": a.get("inheritedFrom"),
                    "projectRole": a.get("projectRole"),
                }
                for a in space.get("access") or []
            ],
            "groups": [pick(g, "groupUuid", "groupName", "spaceRole") for g in space.get("groupsAccess") or []],
        }

    @server.tool(annotations=CREATE)
    async def grant_project_access(project_uuid: Uuid, email: str, role: ProjectRole) -> str:
        """Give an organization member direct access to a project. Fails if they already have a direct grant:
        use update_project_access to change it."""
        async with lightdash(provider) as ld:
            await ld.request(
                "POST", f"/api/v1/projects/{project_uuid}/access", json={"email": email, "role": role, "sendEmail": False}
            )
        return f"Granted {role} on the project to {email}."

    @server.tool(annotations=WRITE)
    async def update_project_access(project_uuid: Uuid, user_uuid: Uuid, role: ProjectRole) -> str:
        """Change a user's direct project role."""
        async with lightdash(provider) as ld:
            await ld.request("PATCH", f"/api/v1/projects/{project_uuid}/access/{user_uuid}", json={"role": role})
        return f"Changed the user's project role to {role}."

    @server.tool(annotations=DESTRUCTIVE)
    async def revoke_project_access(project_uuid: Uuid, user_uuid: Uuid, dry_run: bool = False) -> dict[str, Any]:
        """Remove a user's direct project grant. Access through their organization role or a group remains.
        Use dry_run to see the grant that would be removed."""
        async with lightdash(provider) as ld:
            members = await ld.get(f"/api/v1/projects/{project_uuid}/access")
            member = next((m for m in members if m["userUuid"] == user_uuid), None)
            if member is None:
                return {"removed": None, "message": "This user has no direct grant on the project."}
            grant = {"userUuid": user_uuid, "email": member.get("email"), "role": member.get("role")}
            if dry_run:
                return {"wouldRemove": grant}
            await ld.request("DELETE", f"/api/v1/projects/{project_uuid}/access/{user_uuid}")
        return {"removed": grant}

    @server.tool(annotations=WRITE)
    async def add_group_member(group_uuid: Uuid, user_uuid: Uuid) -> str:
        """Add a user to a group."""
        async with lightdash(provider) as ld:
            await ld.request("PUT", f"/api/v1/groups/{group_uuid}/members/{user_uuid}")
        return "The user is a member of the group."

    @server.tool(annotations=DESTRUCTIVE)
    async def remove_group_member(group_uuid: Uuid, user_uuid: Uuid, dry_run: bool = False) -> dict[str, Any]:
        """Remove a user from a group, and with it any access the group gave them.
        Use dry_run to check the membership first."""
        async with lightdash(provider) as ld:
            members = await ld.get(f"/api/v1/groups/{group_uuid}/members")
            member = next((m for m in members if m["userUuid"] == user_uuid), None)
            if member is None:
                return {"removed": None, "message": "This user is not a member of the group."}
            membership = {"userUuid": user_uuid, "email": member.get("email")}
            if dry_run:
                return {"wouldRemove": membership}
            await ld.request("DELETE", f"/api/v1/groups/{group_uuid}/members/{user_uuid}")
        return {"removed": membership}
