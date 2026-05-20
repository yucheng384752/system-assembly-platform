# Kit Development Standard

This standard defines how extracted kits and future add-on kits must be written.
It exists because extraction starts from user-provided code, while later product
growth depends on predictable kit boundaries.

## Required Manifest Contract

Every kit must declare these fields:

- `id`: stable kebab-case identifier, for example `upload-validation-kit`
- `displayName`: user-facing Traditional Chinese name
- `category`: one of the supported GUI category keys
- `capability`: short business capability statement
- `dependencies`: required kit ids
- `sourcePaths`: source files copied from the mature system
- `subfeatures`: independently selectable business functions
- `backend.routerRegistrations`: FastAPI routers contributed by the kit
- `frontend`: tabs, routes, components, or entry points contributed by the kit
- `database`: models, migrations, seed data, and connection assumptions
- `permissions`: required roles or tenant scopes
- `entitlement`: paid/custom gating rules when applicable
- `options`: user-tunable settings such as colors, chart style, or validation mode

## Subfeature Rules

Use subfeatures when a user can reasonably buy, enable, disable, or customize a
piece of functionality without changing the entire kit.

Good subfeatures:

- PDF to CSV conversion
- chart summary rendering
- form validation rule editor
- import job creation

Avoid subfeatures that are only technical slices:

- one helper function
- one SQLAlchemy model
- one React hook
- one utility file

## Source And Template Rules

Extracted code remains the preferred source of truth. Templates are used only
when a selected kit contributes new standardized infrastructure that does not
exist in the source system yet.

New template files should live under:

```text
templates/backend/<kit-id>/
templates/frontend/<kit-id>/
```

Templates must be registered in the manifest. Assembly tools should discover
them from the resolved plan instead of relying on hidden copy logic.

## Database Rules

The generated system owns one database connection contract. Kits do not create
their own independent database wiring unless they declare an external service.

Each kit may declare:

- models
- migrations
- seed data
- indexes
- required environment variables

The assembly engine is responsible for combining those declarations into a
database plan and generated migration/start scripts.

## Entitlement Rules

Paid or custom features must be declared in the manifest. Examples include:

- PDF to CSV
- form analysis
- chart summary rendering
- custom validation rules

Runtime code should check entitlement through a shared entitlement service or
middleware. Business code should not hard-code customer names or subscription
logic.

## Runtime Script Contract

Every generated package must include:

```text
scripts/check-prerequisites.ps1
scripts/install.ps1
scripts/migrate.ps1
scripts/start.ps1
.env.example
package-manifest.json
dependency-manifest.json
README.md
```

The scripts must be executable after extraction. If dependencies, migration
files, or runtime manifests are missing, scripts must stop with a clear message
that tells the developer which contract to add.

## Acceptance Checklist

A kit is not complete until:

- recipe validation passes
- resolver output includes the kit in the expected order
- backend router registry is generated
- frontend tab registry is generated when frontend exists
- database plan includes required database declarations
- entitlement plan includes paid/custom gates
- generated system validation passes
- package folder validation passes
- relevant tests are added or updated
