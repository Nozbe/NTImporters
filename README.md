# NTImporters

**NTImporters** imports data into [Nozbe](https://nozbe.app) from other task-management / to-do apps, via their public APIs.

Supported APIs:

- Asana - [API](https://developers.asana.com/docs/asana)
- Trello - [API](https://developer.atlassian.com/cloud/trello/rest/api-group-actions/)
- Todoist - [API](https://developer.todoist.com/api/v1/)
- Monday - [API](https://developer.monday.com/api-reference/)

Nozbe API - https://nozbe.com/api

## Usage

The Nozbe app uses **NTImporters** directly.

1. Sign up or log in at https://nozbe.app
2. Go to `Settings -> Importers` and choose the source app
3. Provide the source app's `Personal Access Token` / `API key`
   (see the [help page](https://nozbe.help/advancedfeatures/importers/))
4. Import your data
5. Enjoy Nozbe!

Questions? support@nozbe.com

## Contributing

PRs with new importers or improvements are welcome.

### Contributing guide

- One package per importer in `/src/ntimporters`
- Each importer implements `SPEC` (identifies it) and `run_import` (performs the import)
- `run_import` returns `None` on success, else the error (Nozbe reports it and retries); wrap the import in `ntimporters.nozbe.run_safely`
- An importer only reads its source app; all Nozbe writes go through `ntimporters.nozbe.NozbeImport`:

  ```python
  nz = NozbeImport(nt_auth_token, team_id, "Imported from MyApp")
  nz.check_group(bool(boards))  # before any write; Free team: trial (group is Premium)
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

  `NozbeImport` keeps imported projects in the "Imported from <app>" group. Re-runs are safe: projects match by name, sections and tasks by name within their project, comments by body within their task. Shared rules:

  - Limits: only the import group is checked, upfront (`check_group`); on Free that needs a trial, which lifts all limits; no trial: nothing imported
  - Members matched by email; the token owner is the importing user
  - Recurrence (`recurrence=(rrule, fallback comment)`): set only on an open, due task
  - Reminder (`remind_at=` ms): added if the task has none
  - Due task: to its mapped assignee, else to the author (+ "missing responsibility" tag if the source assignee couldn't be mapped)
  - Task without due date: to its mapped assignee, else nobody
  - Single Tasks: always to the author; tagged with the group name (how re-runs find them), not imported if the tag fails
  - Partial failures (one attachment, one tag) are logged as warnings on the `ntimporters` logger; the import goes on. Auth, plan-limit and server errors stop it

## Development

Requires [uv](https://docs.astral.sh/uv/) (and Java to regenerate the API client).

```sh
uv sync        # create .venv with all dependencies
make lint      # ruff check + format check
make format    # ruff fix + format
make test      # pytest; tests can't reach the network (default API host is production)
```

### Nozbe API client

- `src/openapi_client` is generated from the backend's OpenAPI spec; don't edit it by hand
- Only the APIs in the Makefile's `APIS` are generated; using another API: add its spec tag there
- `tools/slim_client.py` then strips docstrings and the unused `*_with_http_info` / `*_without_preload_content` variants

Regenerate:

```sh
make client                                               # from production spec (what importers run against)
```
