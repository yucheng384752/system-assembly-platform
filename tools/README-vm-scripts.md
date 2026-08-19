# vm_*.py / _win_full_test.py — local dev/debug scripts

These are one-off scripts used to deploy to, and debug against, a developer's own demo VM.
They are not part of the generated system and are not invoked by `test-all.ps1` or any
packaging tool.

None of them hardcode credentials — set these environment variables before running any of
them (only the ones a given script actually needs; each script fails loud with a clear
message if a required one is missing):

| Variable            | Used for                                                        |
|---------------------|-------------------------------------------------------------------|
| `VM_SSH_PASSWORD`   | SSH/SFTP login to the demo VM (paramiko scripts)                  |
| `VM_ADMIN_API_KEY`  | `X-Admin-API-Key` header / `ADMIN_API_KEYS` for the demo backend  |
| `VM_DB_PASSWORD`    | Postgres password on the demo VM (`PGPASSWORD` / DSN)             |

Example (PowerShell):

```powershell
$env:VM_SSH_PASSWORD = "..."
$env:VM_ADMIN_API_KEY = "..."
$env:VM_DB_PASSWORD = "..."
python tools/vm_deploy.py
```

Do not hardcode real values back into these scripts — that is exactly the mistake this file
exists to prevent (see code review finding on hardcoded VM credentials, fixed in this commit).
