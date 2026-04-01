# =====================================================
# VulHunter Makefile
# =====================================================
# 自动探测 Docker / Podman 并执行对应的 compose 命令。
# 无需手动指定 DOCKER_SOCKET_PATH 或 -f docker-compose.podman.yml。
#
# 使用方法:
#   make setup      — 一次性探测运行时，写入根 .env（推荐首次运行）
#   make up         — 从 GHCR 拉取镜像并启动（等效于 compose up -d）
#   make up-build   — 混合构建（frontend+backend 本地构建，runner 拉云端）
#   make up-full    — 全量本地构建
#   make down       — 停止并删除容器
#   make logs       — 查看所有服务日志
#   make ps         — 查看容器状态
# =====================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE_FILES_BASE     := -f docker-compose.yml
COMPOSE_FILES_HYBRID   := -f docker-compose.yml -f docker-compose.hybrid.yml
COMPOSE_FILES_FULL     := -f docker-compose.yml -f docker-compose.full.yml

# ─── 运行时自动探测 ──────────────────────────────────────────────────────────
# 探测顺序: docker compose → podman compose → docker-compose
# 同时探测 Podman socket 并 export DOCKER_SOCKET_PATH
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

# ─── 目标 ───────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "VulHunter Make 目标"
	@echo "──────────────────────────────────────────────────────────"
	@echo "  make setup       一次性探测运行时，写入根 .env"
	@echo "  make up          拉取镜像并启动（后台）"
	@echo "  make up-build    混合构建（frontend+backend 本地）+ 启动"
	@echo "  make up-full     全量本地构建 + 启动"
	@echo "  make down        停止并删除容器"
	@echo "  make logs        跟踪所有服务日志"
	@echo "  make ps          查看容器状态"
	@echo ""
	@echo "  支持的运行时: Docker / Podman（自动探测，无需额外配置）"
	@echo ""

.PHONY: setup
setup:
	@echo "[make] 探测容器运行时并配置根 .env ..."
	@bash scripts/setup-env.sh

.PHONY: up
up:
	@bash scripts/compose-up-with-fallback.sh $(COMPOSE_FILES_BASE) up -d

.PHONY: up-attached
up-attached:
	@bash scripts/compose-up-with-fallback.sh $(COMPOSE_FILES_BASE) up

.PHONY: up-build
up-build:
	@bash scripts/compose-up-with-fallback.sh $(COMPOSE_FILES_HYBRID) up --build -d

.PHONY: up-full
up-full:
	@bash scripts/compose-up-with-fallback.sh $(COMPOSE_FILES_FULL) up --build -d

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

.PHONY: build-backend
build-backend:
	$(DETECT_RUNTIME); \
	$$COMPOSE_CMD $(COMPOSE_FILES_HYBRID) build backend

.PHONY: build-frontend
build-frontend:
	$(DETECT_RUNTIME); \
	$$COMPOSE_CMD $(COMPOSE_FILES_HYBRID) build frontend
