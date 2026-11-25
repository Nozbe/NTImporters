SPEC ?= https://api4.nozbe.com/v1/api/openapi.yaml
GENERATOR ?= uvx --from openapi-generator-cli==7.7.0 openapi-generator-cli
# spec tags of APIs the importers use; add one to use its API
APIS ?= attachments:comments:group_assignments:project_groups:projects:project_sections:reminders:tag_assignments:tags:task_recurrences:tasks:teams:users
client:  # regenerate src/openapi_client from SPEC (file or URL), slimmed; no hand edits there
	rm -rf .client_build
	$(GENERATOR) generate -i $(SPEC) -g python -o .client_build --package-name openapi_client \
		--global-property apis=$(APIS),models,supportingFiles,apiDocs=false,modelDocs=false,apiTests=false,modelTests=false
	uv run python tools/slim_client.py .client_build/openapi_client
	rm -rf src/openapi_client/api src/openapi_client/models
	cp -r .client_build/openapi_client/. src/openapi_client/
	rm -rf .client_build
lint:
	uv run ruff check --output-format=github .
	uv run ruff format --check .
format:
	uv run ruff check --fix .
	uv run ruff format .
test:
	uv run pytest
