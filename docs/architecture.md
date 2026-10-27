# Architecture

The repository is a small monorepo with a React web client and a versioned FastAPI service. The API owns configuration, persistence, validation, and error responses. SQLAlchemy models are registered centrally and schema changes are applied only through Alembic.

`users` represents a flexible person identity. `worker_profiles` is an optional service-provider profile and does not imply verification. `organizations` and `organization_memberships` model business/cooperative participation separately from personal roles. Supabase Auth can later populate `users.external_auth_id` through an explicit authentication adapter without coupling the core domain to a provider.

PostGIS is enabled in the initial migration so future location fields can use native geography/geometry types. No marketplace, payment, authentication, or operational workflow tables are included in Phase 1.

