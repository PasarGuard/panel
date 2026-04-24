# Makefile to check and set up Python 3.14 free-threaded and a virtual environment

PYTHON_VERSION?=3.14t
VENV_DIR=.venv
RUNTIME_ENV=PYTHON_GIL=1 DISABLE_SQLALCHEMY_CEXT_RUNTIME=1 MSGPACK_PUREPYTHON=1

.PHONY: install_uv
install_uv:
	@if ! uv --help >/dev/null 2>&1; then \
		echo "uv not found. Installing..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "uv installed. Ensure ~/.cargo/bin is in your PATH."; \
	else \
		echo "uv is already installed."; \
	fi

# Check if Python 3.14 free-threaded is installed, if not, install it with uv
.PHONY: check-python
check-python: install_uv
	@if ! uv python find $(PYTHON_VERSION) >/dev/null 2>&1; then \
		echo "Python $(PYTHON_VERSION) is not installed. Installing..."; \
		uv python install $(PYTHON_VERSION) || { \
			echo "Failed to install Python $(PYTHON_VERSION). Please install it manually."; \
			exit 1; \
		}; \
	else \
		echo "Python $(PYTHON_VERSION) is installed."; \
	fi

# Install Python dependencies from pyproject.toml
.PHONY: requirements
requirements:
	@uv sync --python $(PYTHON_VERSION)

# Check if nvm is installed, if not, install it
.PHONY: check-nvm
check-nvm:
	@if ! command -v nvm > /dev/null 2>&1; then \
		echo "nvm not found. Installing..."; \
		curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash || { \
			echo "Failed to install nvm. Please install it manually."; \
			exit 1; \
		}; \
		export NVM_DIR="$$HOME/.nvm"; \
		[ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh"; \
		[ -s "$$NVM_DIR/bash_completion" ] && . "$$NVM_DIR/bash_completion"; \
		echo "nvm installed. Version: `nvm --version`"; \
	else \
		echo "nvm is already installed. Version: `nvm --version`"; \
	fi

# Check if nodejs is installed, if not, install it
.PHONY: check-nodejs
check-nodejs: check-nvm
	@if ! node -v > /dev/null 2>&1; then \
		echo "nodejs not found. Installing..."; \
		nvm install 22 || { \
			echo "Failed to install nodejs. Please install it manually."; \
			exit 1; \
		}; \
	else \
		echo "nodejs is already installed."; \
	fi

# Check if bun is installed, if not, install it
.PHONY: check-bun
check-bun: check-nodejs
	@if ! bun --version > /dev/null 2>&1; then \
		echo "bun not found. Installing..."; \
		curl -fsSL https://bun.sh/install | bash || { \
			echo "Failed to install bun. Please install it manually."; \
			exit 1; \
		}; \
	else \
		echo "bun is already installed."; \
	fi

# Install frontend dependencies (Node.js packages)
.PHONY: install-front
install-front: check-bun
	@cd dashboard && bun install 

# Run database migrations using Alembic
.PHONY: run-migration
run-migration:
	@$(RUNTIME_ENV) uv run --python $(PYTHON_VERSION) alembic upgrade head 

.PHONY: check-migrations
check-migrations:
	@$(RUNTIME_ENV) uv run --python $(PYTHON_VERSION) alembic check

# run PasarGuard
.PHONY: run
run:
	@$(RUNTIME_ENV) uv run --python $(PYTHON_VERSION) main.py

# run pasarguard-cli
.PHONY: run-cli
run-cli:
	@$(RUNTIME_ENV) uv run --python $(PYTHON_VERSION) pasarguard-cli.py

# run pasarguard-tui
.PHONY: run-tui
run-tui:
	@$(RUNTIME_ENV) uv run --python $(PYTHON_VERSION) pasarguard-tui.py


# Run tests
.PHONY: test
test:
	@$(RUNTIME_ENV) TESTING=1 DEBUG=0 uv run --python $(PYTHON_VERSION) pytest tests/

# Run tests-watch
.PHONY: test-whatch
test-whatch:
	@$(RUNTIME_ENV) TESTING=1 DEBUG=0 uv run --python $(PYTHON_VERSION) ptw

# Run PasarGuard with Uvicorn reload
.PHONY: run-watch
run-watch:
	@echo "Running application with reload enabled..."
	@$(RUNTIME_ENV) DEBUG=1 uv run --python $(PYTHON_VERSION) main.py

# Check code
.PHONY: check
check:
	@uv run --python $(PYTHON_VERSION) ruff check .

# Format code
.PHONY: format
format:
	@uv run --python $(PYTHON_VERSION) ruff format .

# Clean the environment
.PHONY: clean
clean:
	@rm -rf $(VENV_DIR)
	@echo "Virtual environment removed."

# Setup environment: check Python, install uv, and sync requirements
.PHONY: setup
setup: install_uv check-python requirements

# Format code (front-end)
.PHONY: fformat
fformat:
	@cd dashboard && bun run prettier . --write
