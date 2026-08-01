.PHONY: clean
clean:
	git clean -Xf out/

.PHONY: docker-smoke
docker-smoke:
	@if [ -z "$(IMAGE)" ]; then echo "ERROR: IMAGE is required (e.g. IMAGE=yt-dlp-server:dev)" >&2; exit 1; fi
	@set -e; \
	platform_flag="$(if $(PLATFORM),--platform $(PLATFORM),)"; \
	echo "Smoke testing $(IMAGE) ($(if $(PLATFORM),$(PLATFORM),native))"; \
	docker run --rm $$platform_flag --entrypoint python "$(IMAGE)" -c "from yt_dlp_server.app import create_app; create_app()" >/dev/null; \
	docker run --rm $$platform_flag --entrypoint ffmpeg "$(IMAGE)" -version >/dev/null; \
	docker run --rm $$platform_flag --entrypoint ffprobe "$(IMAGE)" -version >/dev/null; \
	docker run --rm $$platform_flag --entrypoint yt-dlp "$(IMAGE)" --version >/dev/null; \
	docker run --rm $$platform_flag --entrypoint deno "$(IMAGE)" --version >/dev/null; \
	echo "OK"

.PHONY: docker-build-smoke
docker-build-smoke:
	@if [ -z "$(PLATFORM)" ]; then echo "ERROR: PLATFORM is required (e.g. PLATFORM=linux/amd64)" >&2; exit 1; fi
	@set -e; \
	tag="$(if $(TAG),$(TAG),local-smoke)"; \
	ver="$(if $(SETUPTOOLS_SCM_PRETEND_VERSION),$(SETUPTOOLS_SCM_PRETEND_VERSION),$$(uv run python -c 'from importlib.metadata import version; print(version(\"yt-dlp-server\"))'))"; \
	echo "Building $$tag for $(PLATFORM) (version=$$ver)"; \
	docker buildx build --load --platform "$(PLATFORM)" \
		--build-arg "SETUPTOOLS_SCM_PRETEND_VERSION=$$ver" \
		-t "$$tag" .; \
	$(MAKE) docker-smoke IMAGE="$$tag" PLATFORM="$(PLATFORM)"

.PHONY: docker-build-smoke-all
docker-build-smoke-all:
	$(MAKE) docker-build-smoke TAG="$${TAG:-local-smoke}-amd64" PLATFORM=linux/amd64
	$(MAKE) docker-build-smoke TAG="$${TAG:-local-smoke}-arm64" PLATFORM=linux/arm64

.PHONY: fmt
fmt:
	uv run ruff format .
	uv run ruff check --fix .

.PHONY: lint
lint:
	uv run ruff format --check .
	uv run ruff check .

.PHONY: typecheck
typecheck:
	uv run mypy .

.PHONY: test
test:
	uv run python -m pytest -q

.PHONY: check
check: lint typecheck test
