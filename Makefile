SPEC ?= https://api4.nozbe.com/v1/api/openapi.yaml
GENERATOR ?= uvx --from openapi-generator-cli==7.7.0 openapi-generator-cli
client:  # regenerate src/openapi_client from SPEC (file or URL); no hand edits there
	rm -rf .client_build
	$(GENERATOR) generate -i $(SPEC) -g python -o .client_build --package-name openapi_client \
		--global-property apiDocs=false,modelDocs=false,apiTests=false,modelTests=false
	rm -rf src/openapi_client/api src/openapi_client/models
	cp -r .client_build/openapi_client/. src/openapi_client/
	rm -rf .client_build
lint:
	uv run ruff check --output-format=github .
test:
	uv run pytest
