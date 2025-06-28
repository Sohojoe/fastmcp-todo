# FastMCP Todo Server

A simple todo management server built with FastMCP 2.

## Features

- Create, update, and delete todos
- Set priorities (low, medium, high, urgent) and categories
- Mark todos as completed or in progress
- Search and filter todos
- Track due dates and overdue items
- Get todo statistics

## Installation

Install dependencies:
```bash
uv sync
```

## Usage

Run the server:

```bash
uv run python server.py
```

## Testing

Run tests:

```bash
uv run pytest
```

## Tools Available

- `create_todo` - Create a new todo
- `list_todos` - List all todos (with optional filters)
- `update_todo` - Update an existing todo
- `complete_todo` - Mark a todo as completed
- `delete_todo` - Delete a todo
- `search_todos` - Search todos by text
- `get_todo_stats` - Get statistics about todos

## Data Storage

Todos are stored in `tasks.json` in the project directory.
