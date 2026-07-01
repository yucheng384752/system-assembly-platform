# Tools Placeholder

Future tools for this project:

1. `validate-json.ps1`
   Validate JSON files with explicit UTF-8 decoding on Windows PowerShell.

2. `validate-manifest`
   Validate `kits/form-analysis.kit-manifest.json` against
   `schemas/kit.schema.json`.

3. `resolve-recipe.ps1`
   Read `assembly/form-analysis-original.recipe.json`, resolve dependencies, and
   output ordered frontend/backend/database assembly steps.

4. `extract-kit`
   Copy or symlink selected target source files into a generated modular app.

5. `generate-preview`
   Generate mock API payloads and sample data for GUI preview.

6. `extract-mvp-flow.ps1`
   Extract the first MVP source slice into `generated/mvp-import-flow`.
   Use `-DryRun` to preview planned source files without writing output.

7. `package-system.ps1`
   Sync the current generated MVP slice and required specs into a writable
   folder under `dist/`. Use `-CreateZip` only for explicit archive testing;
   the future production zip must be a runnable system package with a startup
   script after extraction.

8. `generate-backend-registry.ps1`
   Generate backend router registry JSON and Python from a resolved plan.

9. `apply-backend-registry.ps1`
   Copy the generated backend router registry into a generated app and replace
   hard-coded FastAPI `include_router` calls with registry-driven registration.

10. `generate-frontend-registry.ps1`
    Generate frontend tab registry JSON and TypeScript from a recipe.

11. `generate-db-plan.ps1`
    Generate database assembly planning data from a resolved plan.

12. `generate-entitlement-plan.ps1`
    Generate paid/entitlement feature checks from selected subfeatures.

13. `assemble-system.ps1`
    Build `dist/generated-system` with selected backend/frontend source,
    scripts, env template, and package manifest. Use `-CreateZip` to produce
    `dist/generated-system.zip`.

14. `test-all.ps1`
    Run the full local validation suite. By default this requires the generated
    frontend production bundle. Use `-SkipFrontendBuild` for offline or
    sandboxed validation when npm install/build is expected to be unavailable or
    too slow; the generated-system structural checks still run.

The current version intentionally starts with specs because the target system
needs confirmed module boundaries before moving code.
