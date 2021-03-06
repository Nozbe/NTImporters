# NTImporters

**NTImporters** helps in importing data to [Nozbe](https://nozbe.app) from other task-management / to-do apps.

**NTImporters** uses publicly available APIs to transfer data between supported apps and [Nozbe](https://nozbe.app).

List of supported APIs:

- Asana - [API](https://developers.asana.com/docs/asana)
- Trello [API](https://developer.atlassian.com/cloud/trello/rest/api-group-actions/)
- Todoist [API](https://developer.todoist.com/rest/v1/#overview)
- Monday [API](https://developer.todoist.com/rest/v1/#overview)
- ...

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
