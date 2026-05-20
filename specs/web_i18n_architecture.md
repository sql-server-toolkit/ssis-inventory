# Web and i18n Architecture - SSIS Inventory

Issue: https://github.com/sql-server-toolkit/ssis-inventory/issues/1
Branch: `feature/web-ui-i18n`

## 1. Objective

Expose SSIS Inventory through a free web experience while preserving the
existing CLI flow. The web experience must support PT-BR, EN and ES for input
texts, interface messages and user-facing output guidance.

## 2. Target Architecture

The MVP architecture is:

- static front-end for language selection, upload, execution parameters,
  progress and report download;
- FastAPI backend for upload orchestration, temporary storage, validation,
  execution of the existing Python inventory routine and report download;
- temporary filesystem usage only;
- Excel and JSON reports available for download for a limited time;
- no permanent persistence of uploaded SSIS projects or generated reports.

The current CLI must remain supported:

```powershell
python -m app.main --project-folder "<project_folder>" --output-folder "./output"
```

## 3. Backend Decision

Backend framework: FastAPI.

Execution server: Uvicorn.

Reasoning:

- native fit for HTTP APIs;
- good support for multipart uploads;
- typed request parameters;
- automatic OpenAPI documentation;
- straightforward automated tests with `TestClient`;
- low coupling when handlers call service functions instead of parser internals.

The backend must not contain SSIS parsing rules directly in HTTP handlers. The
handlers should orchestrate upload, validation, temporary workspace lifecycle,
service execution, downloads and cleanup.

## 4. Front-end Decision

Front-end strategy: static HTML/CSS/JavaScript without a framework for the MVP.

Reasoning:

- minimal dependencies;
- no build step required;
- easy free static hosting;
- current repository already contains `index.html`;
- enough for language selection, upload, parameters, progress states and
  download links.

Suggested structure:

```text
index.html
web/styles.css
web/app.js
web/i18n.js
```

An alternative split for translations is acceptable:

```text
web/i18n/pt-BR.json
web/i18n/en.json
web/i18n/es.json
```

The front-end must call the FastAPI backend using `fetch` and `FormData`.

## 5. Upload Contract

The MVP accepts one `.zip` file per execution.

Multipart field:

```text
project_archive
```

Expected request content type:

```text
multipart/form-data
```

Accepted top-level upload extension:

```text
.zip
```

Accepted contents inside the archive:

- `.dtproj`
- `.dtsx`
- `.conmgr`
- `.ispac`
- auxiliary files required by the SSIS project

Minimum valid structure:

- at least one `.dtproj` or one `.dtsx` must be found after extraction.

The backend must reject:

- empty archives;
- corrupted archives;
- password-protected archives;
- archives with absolute paths;
- archives with entries that escape the temporary workspace;
- archives exceeding operational limits.

Loose multi-file upload is out of scope for the MVP because it can lose folder
structure and increase user error.

## 6. Interface Parameters

The web interface exposes the following parameters.

| Field | Type | Values | Default | Backend mapping |
| --- | --- | --- | --- | --- |
| `ui_language` | select | `auto`, `pt-BR`, `en`, `es` | `auto` | front-end only |
| `report_language` | select | `pt-BR`, `en`, `es` | resolved UI language | report i18n |
| `ignore_disabled` | toggle | `true`, `false` | `true` | `AppConfig.ignore_disabled` |
| `ignore_sql_comments_for_objects` | toggle | `true`, `false` | `true` | `AppConfig.ignore_sql_comments_for_objects` |
| `json_output_mode` | select | `compact`, `full` | `compact` | `AppConfig.json_output_mode` |
| `include_raw_sheets` | toggle | `true`, `false` | `true` | `AppConfig.include_raw_sheets` |
| `ignore_temp_tables` | toggle | `true`, `false` | `true` | `AppConfig.ignore_temp_tables` |
| `temp_table_prefixes` | text | comma-separated prefixes | `#` | `AppConfig.temp_table_prefixes` |

Out of MVP:

- `include_raw_sql_in_json`
- `max_sql_preview_chars`

The backend must apply safe defaults when a parameter is missing.

## 7. Language Detection

When `ui_language=auto`, the front-end must inspect:

- `navigator.languages`
- `navigator.language`

Mapping rules:

- `pt`, `pt-BR` and Portuguese variants map to `pt-BR`;
- `es` and Spanish variants map to `es`;
- `en` and English variants map to `en`;
- unsupported languages fall back to `en`.

If the user manually selects a language different from `auto`, the front-end
may persist that preference in browser storage.

## 8. Temporary File Lifecycle

Each execution creates a random `job_id` using UUID or a secure token.

Temporary root:

- `SSIS_INVENTORY_WORK_DIR`, when configured;
- otherwise the operating system temporary directory.

Workspace layout:

```text
{work_root}/{job_id}/upload/
{work_root}/{job_id}/project/
{work_root}/{job_id}/output/
{work_root}/{job_id}/metadata.json
```

Lifecycle rules:

- save the uploaded `.zip` only until safe extraction finishes;
- delete `upload/` after successful extraction or validation failure;
- delete `project/` after report generation or processing failure;
- keep only `output/` and `metadata.json` during the download window;
- download window: 30 minutes after job completion;
- maximum absolute retention: 45 minutes;
- cleanup runs on backend startup and best-effort after each job;
- never write temporary files inside the repository;
- never expose physical file paths through the API.

Cleanup logs must include only operational metadata such as `job_id`, status and
error type.

## 9. Operational Limits

Initial MVP limits:

| Limit | Value |
| --- | --- |
| Uploads per execution | 1 `.zip` |
| Maximum compressed upload size | 50 MB |
| Maximum extracted size | 200 MB |
| Maximum zip entries | 2,000 |
| Maximum directory depth | 20 levels |
| Maximum single extracted file size | 50 MB |
| Upload timeout | 60 seconds |
| Processing timeout | 5 minutes |
| Active jobs per instance | 1 |
| Queued jobs | 3 |
| Download TTL | 30 minutes |
| Maximum absolute job retention | 45 minutes |
| Maximum generated reports size | 100 MB total |

These limits must be configurable with environment variables:

```text
SSIS_MAX_UPLOAD_MB
SSIS_MAX_EXTRACTED_MB
SSIS_MAX_ZIP_ENTRIES
SSIS_JOB_TIMEOUT_SECONDS
SSIS_MAX_ACTIVE_JOBS
SSIS_MAX_QUEUED_JOBS
SSIS_DOWNLOAD_TTL_MINUTES
```

When a limit is exceeded, the backend must return a translatable error and clean
up any temporary files already created.

## 10. Privacy and Safety Limits

The web flow must follow these privacy limits:

- do not persist uploaded files, extracted files or reports permanently;
- do not keep job history after expiration;
- do not create a database containing package content, connection strings,
  server names, users, internal paths or extracted SQL;
- do not log complete connection strings;
- do not log extracted SQL, package XML, full uploaded filenames or internal
  project paths;
- allowed logs: `job_id`, timestamps, status, upload size, duration, aggregate
  file counts, error type and translatable error code;
- mask sensitive values that appear in exceptions before logging or returning
  messages;
- return generic errors when the failure may expose package internals;
- show a pre-upload warning that SSIS projects may contain sensitive data;
- require a checkbox confirmation that the user is authorized to process the
  files;
- state the retention policy clearly in the UI;
- do not use uploaded files for training, content analytics, public examples or
  any purpose outside report generation;
- do not send SSIS files to third-party services beyond the selected hosting
  infrastructure;
- require HTTPS in published environments.

## 11. API Contract

The API shape for the MVP is:

```text
POST /api/inventory
GET  /api/inventory/{job_id}
GET  /api/inventory/{job_id}/download/excel
GET  /api/inventory/{job_id}/download/json
```

`POST /api/inventory` receives:

- `project_archive`
- execution parameters listed in this spec

The response should include:

- `job_id`
- status
- translatable message code
- download links when available

Processing may start synchronous for the local MVP, but the API shape must allow
status polling if asynchronous execution is introduced.

## 12. Publishing Platform

MVP publishing decision:

- front-end: GitHub Pages;
- backend: Render Free Web Service running FastAPI/Uvicorn.

Accepted Render Free restrictions for the MVP:

- cold start after inactivity;
- ephemeral filesystem;
- no permanent storage;
- no scaling beyond one free instance;
- possible suspension when monthly limits are exceeded;
- not suitable for critical production usage.

Fallbacks:

- Koyeb Free Instance if Render does not fit upload, timeout or availability
  needs;
- Google Cloud Run Free Tier if more container-level control is required and
  billing, budgets and alerts are configured.

## 13. Implementation Boundaries

The implementation must preserve the CLI.

Recommended service boundary:

```python
run_inventory(project_folder, output_folder, config)
```

The FastAPI layer should call this service instead of duplicating the logic from
`app.main`.

Report internationalization is tracked separately and may be applied
incrementally. The API may accept `report_language` before all report text is
fully translated.
