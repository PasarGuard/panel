# Contribute to PasarGuard

Thanks for considering contributing to **PasarGuard**!

## 🙋 Questions

Please **don’t use GitHub Issues** to ask questions. Instead, use one of the following platforms:

-   💬 Telegram: [@Pasar_Guard](https://t.me/pasar_guard)
-   🗣️ GitHub Discussions: [PasarGuard Discussions](https://github.com/pasarguard/panel/discussions)

## 🐞 Reporting Issues

When reporting a bug or issue, please include:

-   ✅ What you expected to happen
-   ❌ What actually happened (include server logs or browser errors)
-   ⚙️ Your `xray` JSON config and `.env` settings (censor sensitive info)
-   🔢 Your PasarGuard version and Docker version (if applicable)

---

# 🚀 Submitting a Pull Request

If there's no open issue for your idea, consider opening one for discussion **before submitting a PR**.

You can contribute to any issue that:

-   Has no PR linked
-   Has no maintainer assigned

No need to ask for permission!

## 🔀 Branching Strategy

-   Always branch off of the `next` branch
-   Keep `main` stable and production-ready

---

# 📁 Project Structure

```text
.
├── app          # Backend code (FastAPI - Python)
├── cli          # CLI code (Typer - Python)
├── dashboard    # Frontend code (React Router - TypeScript)
└── tests        # API tests
```

---

## ⚙️ Development Setup

The project uses [uv](https://github.com/astral-sh/uv) for Python dependency management and [bun](https://bun.sh/) for frontend dependencies.

### 🐍 Backend Setup

1. Install `uv` if you haven't already.
2. Initialize the virtual environment and install dependencies:
   ```bash
   make setup
   ```
3. Run database migrations:
   ```bash
   make run-migration
   ```
4. Start the application:
   ```bash
   make run
   ```

### 💻 Frontend Setup

1. Install `bun` if you haven't already.
2. Install frontend dependencies:
   ```bash
   make install-front
   ```

---

## 🧠 Backend (FastAPI)

The backend is built with **FastAPI** and **SQLAlchemy**:

-   **Pydantic models**: [app/models/](file:///home/coder/panel/app/models)
-   **Database structure**: [app/db/](file:///home/coder/panel/app/db)
    -   SQLAlchemy models: [app/db/models.py](file:///home/coder/panel/app/db/models.py)
    -   Database CRUD operations: [app/db/crud/](file:///home/coder/panel/app/db/crud)
    -   Alembic migrations: [app/db/migrations/](file:///home/coder/panel/app/db/migrations)
-   **Core backend logic**: [app/operation/](file:///home/coder/panel/app/operation)
-   **API Routers**: [app/routers/](file:///home/coder/panel/app/routers)

🧩 **Note**: Ensure **all core backend business logic is organized and implemented in the `app/operation` module**. This keeps route handling, database access, and service logic clearly separated and easier to maintain.

### 📘 API Docs (Swagger / ReDoc)

Enable the `DOCS` flag in your `.env` file to access:

-   Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
-   ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 🎯 Code Formatting & Linting

Format and lint backend Python code with:

```bash
make check
make format
```

### 🗃️ Database Migrations

Apply Alembic migrations to your database:

```bash
make run-migration
```

Check migrations integrity:

```bash
make check-migrations
```

---

## 💻 Frontend (React + Tailwind)

> ⚠️ **We no longer upload pre-built frontend files.**

The frontend is located in the [dashboard/](file:///home/coder/panel/dashboard) directory and is built using:

-   **React Router 7 + TypeScript**
-   **Tailwind CSS v4 + Shadcn UI**
-   **Orval** (for API client generation)

### 🔄 API Client Generation

The frontend uses generated API clients via Orval. If you change backend routes or models, regenerate the TypeScript client by running:

```bash
make gen-api
```

### 🎯 Code Formatting

Format frontend code using Prettier:

```bash
make fformat
```

### 🧩 Component Guidelines

-   Follow **Tailwind + Shadcn** best practices.
-   Keep components **single-purpose**.
-   Prioritize **readability** and **maintainability**.

---

## 🛠️ PasarGuard CLI

PasarGuard’s CLI is built using [Typer](https://typer.tiangolo.com/).

-   CLI codebase: [cli/](file:///home/coder/panel/cli) and the entrypoint script [pasarguard-cli.py](file:///home/coder/panel/pasarguard-cli.py).
-   To run the CLI in development:
    ```bash
    make run-cli
    ```

---

## 🧪 Testing

We use [pytest](https://docs.pytest.org/) for backend tests.

-   Run tests:
    ```bash
    make test
    ```
-   Run tests in watch mode:
    ```bash
    make test-whatch
    ```

---

## 🐛 Debug Mode

To run the project in debug mode with auto-reload, set `DEBUG=true` in your `.env` file.

When you run `make run` (or `uv run main.py`) with `DEBUG=true`:
1. The backend FastAPI server starts in reload mode via Uvicorn.
2. The frontend Vite dev server (`bun run dev`) automatically spins up on a separate port.
3. The API client generator runs in the background to keep the frontend types in sync.

Install frontend dependencies first before running in debug mode:

```bash
make install-front
```

> 💡 **Note**: In production mode (`DEBUG=false`), the backend will check if the `dashboard/build` directory exists. If it doesn't, it will build the frontend once using `bun run build` and then mount and serve the static files from `dashboard/build/` at `/dashboard/`.

---

Feel free to reach out via [Telegram](https://t.me/pasar_guard) or GitHub Discussions if you have any questions. Happy contributing! 🚀
