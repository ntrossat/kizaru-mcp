# Tools

Every tool runs as the signed-in user. A tool fails with a permission message when the user's Lightdash role doesn't allow the call.

Write tools are marked idempotent where repeating them changes nothing. Destructive tools are marked destructive and take `dry_run`, which shows what would change without changing it.

## Read

| Tool | Parameters | Returns | Lightdash API |
| --- | --- | --- | --- |
| `list_projects` | | Projects the user can see | `/api/v1/org/projects` |
| `list_users` | `search` | Organization members with role, status and groups | `/api/v1/org/users` |
| `list_groups` | `search` | Groups and their members | `/api/v1/org/groups` |
| `list_roles` | | System and custom roles with their permission scopes | `/api/v2/orgs/{org}/roles` |
| `list_project_access` | `project_uuid` | Each user's effective role, their direct grant, and the groups with access | `/org/users?projectUuid=`, `/projects/{p}/access`, `/projects/{p}/groupAccesses` |
| `list_spaces` | `project_uuid` | Spaces, nested ones included, with content counts | `/projects/{p}/spaces` |
| `list_space_access` | `project_uuid`, `space_uuid` | Who can access a space and why: direct, or inherited | `/projects/{p}/spaces/{s}` |
| `find_unused_content` | `project_uuid`, `unused_days` (90), `content_type` | Charts and dashboards not viewed in that many days, never-viewed first. Content created within the window is left out | `/api/v2/content` |
| `list_validation_errors` | `project_uuid`, `revalidate` | Broken charts and dashboards from the last validation run, or a fresh one | `/projects/{p}/validate` |
| `list_schedulers` | `project_uuid`, `search` | Scheduled deliveries with schedule, owner, recipients and latest run | `/schedulers/{p}/list` |

## Write

| Tool | Parameters | Does | Lightdash API |
| --- | --- | --- | --- |
| `grant_project_access` | `project_uuid`, `email`, `role` | Gives a member a direct project role, without an email. Fails when a direct grant exists | `POST /projects/{p}/access` |
| `update_project_access` | `project_uuid`, `user_uuid`, `role` | Changes a direct project role | `PATCH /projects/{p}/access/{u}` |
| `revoke_project_access` | `project_uuid`, `user_uuid`, `dry_run` | Removes a direct grant. Access through the organization role or a group remains | `DELETE /projects/{p}/access/{u}` |
| `add_group_member` | `group_uuid`, `user_uuid` | Adds a user to a group | `PUT /groups/{g}/members/{u}` |
| `remove_group_member` | `group_uuid`, `user_uuid`, `dry_run` | Removes a user from a group, and the access it gave them | `DELETE /groups/{g}/members/{u}` |
| `move_content` | `project_uuid`, `content_type`, `uuid`, `target_space_uuid` | Moves a chart, dashboard or space into another space | `/api/v2/content/{p}/move` |
| `delete_content` | `project_uuid`, `content_type`, `uuid`, `dry_run` | Deletes a chart, dashboard or space with everything in it. `dry_run` on a space lists what it holds | `/api/v2/content/{p}/delete` |
| `set_scheduler_enabled` | `scheduler_uuid`, `enabled` | Pauses or resumes a delivery | `PATCH /schedulers/{s}/enabled` |
| `update_scheduler` | `scheduler_uuid`, `name`, `cron`, `timezone`, `message` | Changes the fields given, keeps the rest | `PATCH /schedulers/{s}` |
| `delete_scheduler` | `scheduler_uuid`, `dry_run` | Deletes a delivery | `DELETE /schedulers/{s}` |

Project roles are `viewer`, `interactive_viewer`, `editor`, `developer` and `admin`.

## Things to know

- Deleting content is permanent on a default Lightdash instance: it doesn't appear in the deleted-content list.
- Lightdash's `PATCH /schedulers/{s}` needs the whole scheduler. `update_scheduler` reads it, applies the changes, and sends it all back.
