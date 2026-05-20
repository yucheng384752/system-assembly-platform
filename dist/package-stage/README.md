# Form System Kit Composer

This project decomposes the existing target system into selectable system kits and
defines how those kits can be recomposed into the original application.

Target system:

`C:\Users\gslab\Desktop\Form-analysis-server-specify-kit`

Suggested product name:

**Form System Kit Composer**

## Goal

Turn the completed Form Analysis system into a kit-based architecture:

1. Users select business capabilities from a GUI.
2. Each selection maps to one or more SDK kits.
3. Each kit describes frontend, backend, API, database, permissions, config, preview data, and dependencies.
4. A recipe recomposes selected kits into a deployable system.

## Current Output

- [System decomposition](docs/system-decomposition.md)
- [Competitor analysis](docs/competitor-analysis.md)
- [Decomposition process](docs/decomposition-process.md)
- [Recomposition architecture](docs/recomposition-architecture.md)
- [Development standards](docs/development-standards.md)
- [Product requirements](docs/product-requirements.zh-TW.md)
- [GUI production spec](docs/gui-production-spec.md)
- [TODO](TODO.md)
- [Handoff](HANDOFF.md)
- [Kit manifest](kits/form-analysis.kit-manifest.json)
- [Original-system recipe](assembly/form-analysis-original.recipe.json)
- [MVP import flow recipe](assembly/mvp-import-flow.recipe.json)
- [Kit schema](schemas/kit.schema.json)
- [Operable GUI prototype](gui/index.html)

## How To Use This Project

Use the kit manifest as the source of truth for modularization. The first phase is
not to move code immediately. The first phase is to confirm module boundaries,
dependencies, and source ownership.

Recommended next sequence:

1. Confirm the kit list and dependencies.
2. Pick one vertical slice, preferably `tenant-auth-kit` + `upload-validation-kit`.
3. Extract shared runtime code into `platform-core-kit`.
4. Wrap frontend pages and backend routers behind kit registration.
5. Build a GUI composer that edits the recipe JSON.
6. Generate app assembly from the recipe.
