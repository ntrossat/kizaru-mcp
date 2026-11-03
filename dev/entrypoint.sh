#!/bin/bash
# Upstream examples/full-jaffle-shop-demo/entrypoint.sh, with two fixes:
# - reset the Lightdash schemas instead of `rollback --all`, which fails on irreversible migrations
# - create the enterprise-only organization_homepage_settings table the seed writes to (no license key here)
set -e

# Idempotent dbt commands
dbt seed --project-dir /usr/app/dbt --profiles-dir /usr/app/profiles --full-refresh
dbt run --project-dir /usr/app/dbt --profiles-dir /usr/app/profiles

# Runs JavaScript with a knex connection to the Lightdash database
knex_run() {
    (cd /usr/app/packages/backend/dist && node -e "
        const knex = require('knex')(require('./knexfile').default.production);
        (async () => { $1 })().finally(() => knex.destroy());
    ")
}

# Reset the Lightdash schemas (dbt data lives in jaffle), migrate and seed
knex_run "await knex.raw('drop schema if exists public, graphile_worker cascade; create schema public');"
pnpm -F backend migrate-production
knex_run "
    const dir = './ee/database/migrations/';
    const file = require('fs').readdirSync(dir).find((f) => f.endsWith('_create_organization_homepage_settings.js'));
    await require(dir + file).up(knex);
"
pnpm -F backend seed-production
exec "$@"
