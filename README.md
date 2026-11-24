# NTImporters

**NTImporters** helps in importing data to [Nozbe](https://nozbe.app) from other task-management / to-do apps.

**NTImporters** uses publicly available APIs to transfer data between supported apps and [Nozbe](https://nozbe.app).

List of supported APIs:

- Asana - [API](https://developers.asana.com/docs/asana)
- Trello - [API](https://developer.atlassian.com/cloud/trello/rest/api-group-actions/)
- Todoist - [API](https://developer.todoist.com/api/v1/)
- Monday - [API](https://developer.monday.com/api-reference/)
- Microsoft To Do - [API](https://learn.microsoft.com/en-us/graph/api/resources/todo-overview)

Nozbe API - https://nozbe.com/api

## Usage

**NTImporters** is used directly by the Nozbe app.

1. Sign up or log in at https://nozbe.app
2. Go to `Settings -> Importers` and choose application to import data from
3. Provide `Personal Access Token` / `API key` to your account registered in application selected in step 2
   (Microsoft To Do: an access token from Graph Explorer, see the [help page](https://nozbe.help/advancedfeatures/importers/)).
4. Import your data
5. Enjoy Nozbe!

Questions? Contact support: support@nozbe.com

## Contributing

You are welcome to contribute to **NTImporters** project by creating PRs with implementations of new importers or improvements to existing ones.

### Contributing guide

- Each importer should be located in a separate package in `/src/ntimporters`
- Each importer should implement `SPEC` to identify importer and `run_import` method for performing import
- `run_import` returns `None` on success, otherwise the error (Nozbe4Backend reports it to Sentry and retries the import); wrap the import in `ntimporters.nozbe.run_safely`
- An importer only reads its source app; all writing to Nozbe goes through `ntimporters.nozbe.NozbeImport`:

  ```python
  nz = NozbeImport(nt_auth_token, team_id, "Imported from MyApp")
  nz.check_open_projects(board["name"] for board in boards)
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

  It keeps imported projects in the "Imported from <app>" group and makes re-runs safe: projects match by name, sections and tasks by name within their project, comments by body within their task. Shared rules live there too: limits (projects imported before don't count; sections checked per project as created), members matched by email (the token owner is the importing user), a new task's recurrence (`recurrence=(rrule, fallback comment)`) is set only if it is due, a reminder (`remind_at=` ms) only on a new task, a due task goes to its mapped assignee, else to the author (with a "missing responsibility" tag if the source assignee couldn't be mapped), tasks without due date have no responsible person, Single Tasks are the author's.
- Partial failures (one attachment, one tag) are logged as warnings on the `ntimporters` logger and don't stop the import

## Development

Requires [uv](https://docs.astral.sh/uv/) (and Java for regenerating the API client).

```sh
uv sync        # create .venv with all dependencies
make lint      # ruff check + format check
make format    # ruff fix + format
make test      # pytest; tests can't reach the network (default API host is production)
```

Run an importer against a local or dev Nozbe backend:

```sh
export CUSTOM_API_HOST=http://localhost:8888/v1/api   # or DEV_ACCESS_TOKEN=... for devapi4
uv run python -c "from ntimporters.todoist import run_import; print(run_import('<nozbe api key>', '<todoist token>', '<team id>'))"
```

### Nozbe API client

`src/openapi_client` is generated from the backend's OpenAPI spec. Don't edit it by hand: customisations (API version header, dev token, 429 retries) live in `ntimporters.utils.nt_api_client`. To regenerate:

```sh
make client                                               # from production spec (what importers run against)
make client SPEC=../Nozbe4Backend/NozbeKinto/nt_api/_build/openapi_bundled.yaml   # unreleased backend changes
```
