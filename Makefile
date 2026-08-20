.PHONY: backend-test frontend-test frontend-build generate-api test

backend-test:
	cd AERIS/backend && python -m unittest discover -s tests -v

generate-api:
	cd AERIS/frontend && npm run generate:api

frontend-test:
	cd AERIS/frontend && npm test

frontend-build: generate-api
	cd AERIS/frontend && npm run build

test: backend-test frontend-test frontend-build
