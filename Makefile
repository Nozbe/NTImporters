client:
	openapi-generator-cli  generate -i https://api4.nozbe.com/v1/api/openapi.yaml -g python -o client_prod
	# review  commits of https://github.com/Nozbe/NTImporters/pull/40/files
client_dev:
	openapi-generator-cli  generate -i http://localhost:8888/v1/api/openapi.yaml -g python -o client_dev
