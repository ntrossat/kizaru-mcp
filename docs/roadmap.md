# Roadmap

## Done

- **OAuth on open-source Lightdash:** checked by hand, see [How Lightdash OAuth behaves](architecture.md#how-lightdash-oauth-behaves).
- **Foundation:** the OAuth provider with its own consent page, encrypted Redis storage, upstream refresh under a lock, the Lightdash client and error mapping.
- **Read tools:** users, groups, roles, project access, spaces and space access, schedulers, validation errors, unused content.
- **Write tools:** project access, group membership, moving and deleting content, pausing, editing and deleting schedulers, with `dry_run` on destructive tools.
- **Data tools:** explores, fields and metric queries, with filters and sorts.
- **Tests:** unit tests, and integration tests on a local Lightdash with an admin and a viewer.

## Next

- [ ] Check the server by hand with MCP Inspector, Claude.ai and ChatGPT as custom connectors, and Claude Code.
- [ ] A Docker image, served over HTTPS with Redis.
- [ ] Log tool calls per user, without data payloads.
- [ ] A PyPI package runnable with `uvx`, and listings in MCP registries.

## Risks

| Risk | Fallback |
| --- | --- |
| A Lightdash instance has no OAuth server | Offer a personal-access-token mode. |
| Lightdash revokes the whole sign-in after a refresh-token reuse | Not the case today. The lock prevents reuse anyway, and a refused refresh ends the grant so the user signs in again. |
| REST endpoints change | The integration tests run every tool against a pinned Lightdash release. Run them against each new one. |
| The MCP SDK v2 still changes in minor releases | The version is pinned below 3. Run the tests on each upgrade. |
