# NTImporters

**NTImporters** helps in importing data to [Nozbe](https://nozbe.app) from other task-management / to-do apps.

**NTImporters** uses publicly available APIs to transfer data between supported apps and [Nozbe](https://nozbe.app).

List of supported APIs:

- Asana - [API](https://developers.asana.com/docs/asana)
- Trello - [API](https://developer.atlassian.com/cloud/trello/rest/api-group-actions/)
- Todoist - [API](https://developer.todoist.com/api/v1/)
- Monday - [API](https://developer.monday.com/api-reference/)

Nozbe API - https://nozbe.com/api

## Usage

**NTImporters** is used directly by the Nozbe app.

1. Sign up or log in at https://nozbe.app
2. Go to `Settings -> Importers` and choose application to import data from
3. Provide `Personal Access Token` / `API key` to your account registered in application selected in step 2.
4. Import your data
5. Enjoy Nozbe!

Questions? Contact support: support@nozbe.com

## Contributing

You are welcome to contribute to **NTImporters** project by creating PRs with implementations of new importers or improvements to existing ones.

### Contributing guide

- Each importer should be located in a separate package in `/src/ntimporters`
- Each importer should implement `SPEC` to identify importer and `run_import` method for performing import
- Imported projects are kept in an "Imported from <app>" project group. Re-running an import matches projects by name, sections and tasks by name within their project, and comments by body within their task, so nothing is duplicated
- Use the shared helpers in `ntimporters.utils` (`nt_api_client`, `exists`, `post_comment`, `assign_tags`, `upload_attachment`, ...) instead of calling the Nozbe API by hand

## Development

Requires [uv](https://docs.astral.sh/uv/) (and Java for regenerating the API client).

```sh
uv sync        # create .venv with all dependencies
make lint      # ruff
make test      # pytest
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
