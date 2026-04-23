# =====================================================
# VulHunter Makefile
# =====================================================
# 只保留 compose 状态/日志辅助命令。
# 启动统一使用以下命令：
#   docker compose up --build
# =====================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE_FILES_BASE := -f docker-compose.yml

define DETECT_RUNTIME
	@if docker compose version >/dev/null 2>&1; then \
		COMPOSE_CMD="docker compose"; \
	elif podman compose version >/dev/null 2>&1; then \
		COMPOSE_CMD="podman compose"; \
		if [ -z "$${DOCKER_SOCKET_PATH:-}" ]; then \
			for _s in /run/podman/podman.sock /var/run/podman/podman.sock \
				/run/user/$$(id -u)/podman/podman.sock; do \
				if [ -S "$$_s" ]; then export DOCKER_SOCKET_PATH="$$_s"; break; fi; \
			done; \
		fi; \
	elif command -v docker-compose >/dev/null 2>&1; then \
		COMPOSE_CMD="docker-compose"; \
	else \
		echo "[ERROR] no compose tool found (docker compose / podman compose / docker-compose)" >&2; \
		exit 1; \
	fi
endef

.PHONY: help
help:
	@echo ""
	@echo "VulHunter Make 目标"
	@echo "──────────────────────────────────────────────────────────"
	@echo "  make down        停止并删除容器"
	@echo "  make logs        跟踪所有服务日志"
	@echo "  make ps          查看容器状态"
	@echo ""
	@echo "  启动请直接使用:"
	@echo "    docker compose up --build"
	@echo ""

.PHONY: down
down:
	$(DETECT_RUNTIME); \
	$$COMPOSE_CMD $(COMPOSE_FILES_BASE) down

.PHONY: logs
logs:
	$(DETECT_RUNTIME); \
	$$COMPOSE_CMD $(COMPOSE_FILES_BASE) logs -f

.PHONY: ps
ps:
	$(DETECT_RUNTIME); \
	$$COMPOSE_CMD $(COMPOSE_FILES_BASE) ps
