# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Server
```bash
uv run python server.py
```

### Installing Dependencies
```bash
uv sync
```

### Running Tests
```bash
uv run pytest
```

### Running Specific Tests
```bash
uv run pytest tests/test_todo_server.py::TestMCPTools::test_add_task_tool
```

## Architecture Overview

This is a FastMCP Todo Server that provides a complete MCP (Model Context Protocol) implementation with three endpoint types:

### Core Components

- **Storage Layer**: Dual storage system that automatically switches between PostgreSQL (when DATABASE_URL is set) and file-based storage (tasks.json)
- **MCP Server**: Built with FastMCP 2, provides tools, resources, and prompts
- **Async Architecture**: All operations are async using asyncio and asyncpg for database operations

### MCP Endpoints

**Tools (Actions)**:
- `add_task` - Create new tasks with priority and due dates
- `complete_task` - Mark tasks as completed
- `delete_task` - Remove tasks from storage
- `update_task_priority` - Change task priority levels
- `list_tasks` - Display tasks with filtering by status

**Resources (Data Access)**:
- `tasks://all` - All tasks
- `tasks://pending` - Uncompleted tasks only
- `tasks://completed` - Completed tasks only
- `tasks://priority/{priority}` - Tasks filtered by priority level
- `tasks://stats` - Task statistics and metrics
- `tasks://task/{task_id}` - Individual task details

**Prompts (AI Templates)**:
- `task_prioritization_prompt` - Help prioritize task lists
- `daily_planning_prompt` - Plan daily task schedules
- `task_breakdown_prompt` - Break complex tasks into steps
- `weekly_review_prompt` - Review completed work
- `smart_daily_planning_prompt` - AI planning with actual task data
- `smart_prioritization_prompt` - AI prioritization analysis
- `overdue_tasks_prompt` - Handle overdue task management

### Data Storage

**Database Mode** (when DATABASE_URL env var is set):
- Uses PostgreSQL with asyncpg connection pooling
- Auto-creates `tasks` table on startup
- Handles datetime objects and proper transaction management

**File Mode** (fallback):
- Stores data in `tasks.json`
- Uses file locking for concurrent access
- Handles JSON serialization/deserialization

### Task Structure
```python
{
    "id": int,              # Auto-incrementing ID
    "title": str,           # Task description
    "priority": str,        # "low", "medium", "high", "urgent"
    "due_date": str|None,   # ISO date string or null
    "created": str,         # ISO datetime string
    "completed": bool,      # Completion status
    "completed_at": str|None # ISO datetime when completed
}
```

## Key Implementation Details

- **Database Initialization**: Uses global `_db_initialized` flag to prevent multiple init calls
- **Error Handling**: Database connection failure gracefully falls back to file storage
- **ID Generation**: IDs increment continuously even after deletions (no ID reuse)
- **Priority Icons**: Uses emoji icons for visual priority representation
- **Datetime Handling**: Consistent ISO format across storage backends
- **Testing**: Comprehensive test suite with temporary file fixtures and database state reset

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (optional, enables database mode)
- `PORT` - HTTP server port (default: 8080)
- `RAILWAY_ENVIRONMENT` - Detected automatically for deployment mode

## Running Modes

The server automatically detects its running mode:
- **STDIO Mode**: For MCP clients (when stdin is not a TTY and not deployed)
- **HTTP Mode**: For web/deployment scenarios (when PORT is set or deployed)