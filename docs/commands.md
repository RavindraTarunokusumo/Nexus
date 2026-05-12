# Commands

The application stack is not implemented yet. Add exact commands here as soon as project tooling lands.

## GitNexus Workflow

Use GitNexus first when you need repo context:

```sh
gitnexus status
gitnexus analyze
gitnexus query "search concept"
gitnexus context <symbol>
gitnexus impact <symbol>
gitnexus detect-changes
gitnexus mcp
```

## Expected Future Commands

```sh
docker compose up
alembic upgrade head
pytest
ruff check .
ruff format --check .
```

These are placeholders based on the FastAPI/PostgreSQL target stack. Replace them with actual repo commands once dependencies and tooling are committed.
