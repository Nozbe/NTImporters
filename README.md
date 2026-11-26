# NTImporters

**NTImporters** imports data into [Nozbe](https://nozbe.app) from other task-management / to-do apps, via their public APIs.

Supported APIs:

- Asana - [API](https://developers.asana.com/docs/asana)
- Trello - [API](https://developer.atlassian.com/cloud/trello/rest/api-group-actions/)
- Todoist - [API](https://developer.todoist.com/api/v1/)
- Monday - [API](https://developer.monday.com/api-reference/)
- Microsoft To Do - [API](https://learn.microsoft.com/en-us/graph/api/resources/todo-overview)

Nozbe API - https://nozbe.com/api

## Usage

In Nozbe: `Settings -> Importers`, pick the app, paste its API token
(Microsoft To Do: Graph Explorer token, see [help](https://nozbe.help/advancedfeatures/importers/)).
Questions: support@nozbe.com

## Contributing

PRs with new importers or improvements are welcome.

- One package per importer in `src/ntimporters`, exposing `SPEC` and `run_import`
- `run_import`: `None` on success, else the error (Nozbe reports it and retries); wrap in `ntimporters.nozbe.run_safely`
- Importers only read their source app; every Nozbe write goes through `ntimporters.nozbe.NozbeImport`:

  ```python
  nz = NozbeImport(nt_auth_token, team_id, "Imported from MyApp")
  nz.check_group(bool(boards))  # before any write
  responsible = nz.members({user["id"]: user["email"] for user in users}, owner=me["id"])
  project_id = nz.project(board["name"], is_favorite=board["starred"])
  section_id = nz.section(project_id, column["name"], position)
  task_id, is_new = nz.task(
      project_id,
      card["name"],
      section_id=section_id,
      due=...,  # date (all day) or datetime
      responsible_id=responsible.get(card["assignee"]),
      assigned=bool(card["assignee"]),
  )
  nz.assign_tags(task_id, tag_ids, is_new)
  nz.comment(task_id, card["description"])
  nz.attachment(task_id, file["name"], file["url"], is_file=True, headers=auth_headers)
  ```

`NozbeImport` rules:

- Projects go into the "Imported from <app>" group. Re-runs add only what's missing: projects match by name, sections and tasks by name in their project, comments by body in their task
- Limits: only the group is checked, upfront (`check_group`). Free team: trial, which lifts all limits; no trial: nothing imported
- Members match by email; the token owner is the author
- Responsible: the mapped assignee; else, for a due task, the author (+ "missing responsibility" tag if the assignee couldn't be mapped); else nobody. Single Tasks: the author; tagged with the group name (how re-runs find them), not imported if the tag fails
- Recurrence (`recurrence=(rrule, fallback comment)`): due tasks only. Reminder (`remind_at=` ms): added if missing
- Errors: a refused record is logged on the `ntimporters` logger and skipped; auth, plan-limit and server errors stop the import

## Development

Requires [uv](https://docs.astral.sh/uv/); Java to regenerate the API client.

```sh
uv sync        # .venv with all dependencies
make lint      # ruff check + format check
make format    # ruff fix + format
make test      # pytest, no network
```

Against a local Nozbe backend:

```sh
export CUSTOM_API_HOST=http://localhost:8888/v1/api   # or DEV_ACCESS_TOKEN=... for a Nozbe dev server
uv run python -c "from ntimporters.todoist import run_import; print(run_import('<nozbe api key>', '<todoist token>', '<team id>'))"
```

### Nozbe API client

`src/openapi_client` is generated; don't edit it. `make client` builds only the APIs in the Makefile's `APIS`
(add a spec tag to use another), then `tools/slim_client.py` strips docstrings and unused method variants.
Customisations (API version header, dev token, 429 retries): `ntimporters.utils.nt_api_client`.

```sh
make client                          # from production spec
make client SPEC=path/to/openapi.yaml
```
