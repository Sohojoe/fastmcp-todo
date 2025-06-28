#!/usr/bin/env python3
"""
FastMCP Todo Server

A comprehensive todo management server built with FastMCP 2.
Provides tools for creating, managing, and organizing todo items with priorities,
categories, and due dates.
"""

import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum

from fastmcp import FastMCP
from pydantic import BaseModel, Field


class Priority(str, Enum):
    """Todo item priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Status(str, Enum):
    """Todo item status."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoItem(BaseModel):
    """A todo item with all its properties."""
    id: int
    title: str
    description: Optional[str] = None
    priority: Priority = Priority.MEDIUM
    status: Status = Status.TODO
    category: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    tags: List[str] = Field(default_factory=list)


class TodoManager:
    """Manages todo items with persistence."""
    
    def __init__(self, data_file: str = "todos.json"):
        self.data_file = Path(data_file)
        self.todos: Dict[int, TodoItem] = {}
        self.next_id = 1
        self.load_todos()
    
    def load_todos(self):
        """Load todos from JSON file."""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.todos = {
                        int(k): TodoItem(**v) for k, v in data.get('todos', {}).items()
                    }
                    self.next_id = data.get('next_id', 1)
            except (json.JSONDecodeError, KeyError):
                # Reset if corrupted
                self.todos = {}
                self.next_id = 1
    
    def save_todos(self):
        """Save todos to JSON file."""
        data = {
            'todos': {str(k): v.model_dump(mode='json') for k, v in self.todos.items()},
            'next_id': self.next_id
        }
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def create_todo(self, title: str, description: Optional[str] = None,
                   priority: Priority = Priority.MEDIUM, category: Optional[str] = None,
                   due_date: Optional[datetime] = None, tags: Optional[List[str]] = None) -> TodoItem:
        """Create a new todo item."""
        todo = TodoItem(
            id=self.next_id,
            title=title,
            description=description,
            priority=priority,
            category=category,
            due_date=due_date,
            tags=tags or []
        )
        self.todos[self.next_id] = todo
        self.next_id += 1
        self.save_todos()
        return todo
    
    def get_todo(self, todo_id: int) -> Optional[TodoItem]:
        """Get a todo by ID."""
        return self.todos.get(todo_id)
    
    def update_todo(self, todo_id: int, **kwargs) -> Optional[TodoItem]:
        """Update a todo item."""
        if todo_id not in self.todos:
            return None
        
        todo = self.todos[todo_id]
        for key, value in kwargs.items():
            if hasattr(todo, key) and value is not None:
                setattr(todo, key, value)
        
        todo.updated_at = datetime.now()
        self.save_todos()
        return todo
    
    def delete_todo(self, todo_id: int) -> bool:
        """Delete a todo item."""
        if todo_id in self.todos:
            del self.todos[todo_id]
            self.save_todos()
            return True
        return False
    
    def list_todos(self, status: Optional[Status] = None, category: Optional[str] = None,
                  priority: Optional[Priority] = None, tag: Optional[str] = None) -> List[TodoItem]:
        """List todos with optional filters."""
        todos = list(self.todos.values())
        
        if status:
            todos = [t for t in todos if t.status == status]
        if category:
            todos = [t for t in todos if t.category == category]
        if priority:
            todos = [t for t in todos if t.priority == priority]
        if tag:
            todos = [t for t in todos if tag in t.tags]
        
        # Sort by priority (urgent first) then by due date
        priority_order = {Priority.URGENT: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
        todos.sort(key=lambda t: (
            priority_order.get(t.priority, 4),
            t.due_date or datetime.max,
            t.created_at
        ))
        
        return todos
    
    def get_overdue_todos(self) -> List[TodoItem]:
        """Get all overdue todos."""
        now = datetime.now()
        return [
            todo for todo in self.todos.values()
            if todo.due_date and todo.due_date < now and todo.status not in [Status.COMPLETED, Status.CANCELLED]
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get todo statistics."""
        total = len(self.todos)
        completed = len([t for t in self.todos.values() if t.status == Status.COMPLETED])
        overdue = len(self.get_overdue_todos())
        by_priority = {}
        by_category = {}
        
        for todo in self.todos.values():
            if todo.status != Status.COMPLETED:
                by_priority[todo.priority] = by_priority.get(todo.priority, 0) + 1
                if todo.category:
                    by_category[todo.category] = by_category.get(todo.category, 0) + 1
        
        return {
            'total': total,
            'completed': completed,
            'pending': total - completed,
            'overdue': overdue,
            'completion_rate': round((completed / total * 100) if total > 0 else 0, 1),
            'by_priority': by_priority,
            'by_category': by_category
        }


# Initialize the todo manager
todo_manager = TodoManager()

# Create FastMCP server
mcp = FastMCP(
    name="Todo Management Server",
    instructions="""
    This server provides comprehensive todo management capabilities.
    
    Available operations:
    - Create todos with title, description, priority, category, due date, and tags
    - List todos with various filters (status, category, priority, tag)
    - Update existing todos
    - Mark todos as completed or change their status
    - Delete todos
    - View overdue todos
    - Get todo statistics
    
    Priority levels: low, medium, high, urgent
    Status values: todo, in_progress, completed, cancelled
    
    Use categories to organize todos by project or area.
    Use tags for flexible labeling and filtering.
    """,
)


@mcp.tool
def create_todo(
    title: str,
    description: str = None,
    priority: str = "medium",
    category: str = None,
    due_date: str = None,
    tags: str = None
) -> dict:
    """
    Create a new todo item.
    
    Args:
        title: The title of the todo item (required)
        description: Optional detailed description
        priority: Priority level (low, medium, high, urgent) - default: medium
        category: Optional category for organization
        due_date: Optional due date in ISO format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
        tags: Optional comma-separated tags for labeling
    
    Returns:
        Dict with the created todo item details
    """
    try:
        # Parse priority
        priority_enum = Priority(priority.lower())
    except ValueError:
        return {"error": f"Invalid priority '{priority}'. Use: low, medium, high, urgent"}
    
    # Parse due date
    parsed_due_date = None
    if due_date:
        try:
            # Try different date formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    parsed_due_date = datetime.strptime(due_date, fmt)
                    break
                except ValueError:
                    continue
            if not parsed_due_date:
                return {"error": f"Invalid date format '{due_date}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"}
        except Exception as e:
            return {"error": f"Date parsing error: {str(e)}"}
    
    # Parse tags
    parsed_tags = []
    if tags:
        parsed_tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
    
    # Create todo
    todo = todo_manager.create_todo(
        title=title,
        description=description,
        priority=priority_enum,
        category=category,
        due_date=parsed_due_date,
        tags=parsed_tags
    )
    
    return {
        "success": True,
        "todo": todo.model_dump(mode='json'),
        "message": f"Todo '{title}' created successfully with ID {todo.id}"
    }


@mcp.tool
def list_todos(
    status: str = None,
    category: str = None,
    priority: str = None,
    tag: str = None,
    limit: int = 50
) -> dict:
    """
    List todo items with optional filters.
    
    Args:
        status: Filter by status (todo, in_progress, completed, cancelled)
        category: Filter by category
        priority: Filter by priority (low, medium, high, urgent)
        tag: Filter by tag
        limit: Maximum number of todos to return (default: 50)
    
    Returns:
        Dict with list of todos and metadata
    """
    # Parse filters
    status_enum = None
    if status:
        try:
            status_enum = Status(status.lower())
        except ValueError:
            return {"error": f"Invalid status '{status}'. Use: todo, in_progress, completed, cancelled"}
    
    priority_enum = None
    if priority:
        try:
            priority_enum = Priority(priority.lower())
        except ValueError:
            return {"error": f"Invalid priority '{priority}'. Use: low, medium, high, urgent"}
    
    # Get filtered todos
    todos = todo_manager.list_todos(
        status=status_enum,
        category=category,
        priority=priority_enum,
        tag=tag
    )
    
    # Apply limit
    limited_todos = todos[:limit]
    
    return {
        "success": True,
        "todos": [todo.model_dump(mode='json') for todo in limited_todos],
        "total_count": len(todos),
        "returned_count": len(limited_todos),
        "filters_applied": {
            "status": status,
            "category": category,
            "priority": priority,
            "tag": tag
        }
    }


@mcp.tool
def get_todo(todo_id: int) -> dict:
    """
    Get a specific todo item by ID.
    
    Args:
        todo_id: The ID of the todo item
    
    Returns:
        Dict with the todo item details or error message
    """
    todo = todo_manager.get_todo(todo_id)
    if not todo:
        return {"error": f"Todo with ID {todo_id} not found"}
    
    return {
        "success": True,
        "todo": todo.model_dump(mode='json')
    }


@mcp.tool
def update_todo(
    todo_id: int,
    title: str = None,
    description: str = None,
    priority: str = None,
    status: str = None,
    category: str = None,
    due_date: str = None,
    tags: str = None
) -> dict:
    """
    Update an existing todo item.
    
    Args:
        todo_id: The ID of the todo item to update (required)
        title: New title
        description: New description
        priority: New priority (low, medium, high, urgent)
        status: New status (todo, in_progress, completed, cancelled)
        category: New category
        due_date: New due date in ISO format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
        tags: New comma-separated tags
    
    Returns:
        Dict with the updated todo item details
    """
    if not todo_manager.get_todo(todo_id):
        return {"error": f"Todo with ID {todo_id} not found"}
    
    updates = {}
    
    # Parse and validate inputs
    if title is not None:
        updates['title'] = title
    
    if description is not None:
        updates['description'] = description
    
    if priority is not None:
        try:
            updates['priority'] = Priority(priority.lower())
        except ValueError:
            return {"error": f"Invalid priority '{priority}'. Use: low, medium, high, urgent"}
    
    if status is not None:
        try:
            updates['status'] = Status(status.lower())
        except ValueError:
            return {"error": f"Invalid status '{status}'. Use: todo, in_progress, completed, cancelled"}
    
    if category is not None:
        updates['category'] = category
    
    if due_date is not None:
        try:
            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    updates['due_date'] = datetime.strptime(due_date, fmt)
                    break
                except ValueError:
                    continue
            if 'due_date' not in updates:
                return {"error": f"Invalid date format '{due_date}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"}
        except Exception as e:
            return {"error": f"Date parsing error: {str(e)}"}
    
    if tags is not None:
        updates['tags'] = [tag.strip() for tag in tags.split(',') if tag.strip()]
    
    # Update the todo
    updated_todo = todo_manager.update_todo(todo_id, **updates)
    
    return {
        "success": True,
        "todo": updated_todo.model_dump(mode='json'),
        "message": f"Todo {todo_id} updated successfully"
    }


@mcp.tool
def complete_todo(todo_id: int) -> dict:
    """
    Mark a todo item as completed.
    
    Args:
        todo_id: The ID of the todo item to complete
    
    Returns:
        Dict with success status and message
    """
    if not todo_manager.get_todo(todo_id):
        return {"error": f"Todo with ID {todo_id} not found"}
    
    updated_todo = todo_manager.update_todo(todo_id, status=Status.COMPLETED)
    
    return {
        "success": True,
        "todo": updated_todo.model_dump(mode='json'),
        "message": f"Todo {todo_id} marked as completed"
    }


@mcp.tool
def delete_todo(todo_id: int) -> dict:
    """
    Delete a todo item.
    
    Args:
        todo_id: The ID of the todo item to delete
    
    Returns:
        Dict with success status and message
    """
    if todo_manager.delete_todo(todo_id):
        return {
            "success": True,
            "message": f"Todo {todo_id} deleted successfully"
        }
    else:
        return {"error": f"Todo with ID {todo_id} not found"}


@mcp.tool
def get_overdue_todos() -> dict:
    """
    Get all overdue todo items.
    
    Returns:
        Dict with list of overdue todos
    """
    overdue_todos = todo_manager.get_overdue_todos()
    
    return {
        "success": True,
        "overdue_todos": [todo.model_dump(mode='json') for todo in overdue_todos],
        "count": len(overdue_todos),
        "message": f"Found {len(overdue_todos)} overdue todo(s)"
    }


@mcp.tool
def get_todo_stats() -> dict:
    """
    Get statistics about todo items.
    
    Returns:
        Dict with various statistics about todos
    """
    stats = todo_manager.get_stats()
    
    return {
        "success": True,
        "statistics": stats,
        "message": "Todo statistics retrieved successfully"
    }


@mcp.tool
def search_todos(query: str, limit: int = 20) -> dict:
    """
    Search for todos by title or description content.
    
    Args:
        query: Search query to match in title or description
        limit: Maximum number of results to return (default: 20)
    
    Returns:
        Dict with matching todos
    """
    query_lower = query.lower()
    all_todos = todo_manager.list_todos()
    
    matching_todos = []
    for todo in all_todos:
        if (query_lower in todo.title.lower() or 
            (todo.description and query_lower in todo.description.lower())):
            matching_todos.append(todo)
    
    # Apply limit
    limited_results = matching_todos[:limit]
    
    return {
        "success": True,
        "todos": [todo.model_dump(mode='json') for todo in limited_results],
        "total_matches": len(matching_todos),
        "returned_count": len(limited_results),
        "query": query,
        "message": f"Found {len(matching_todos)} todo(s) matching '{query}'"
    }


# Resources for exposing todo data
@mcp.resource("todos://all")
def get_all_todos_resource() -> str:
    """Get all todos as a JSON resource."""
    todos = todo_manager.list_todos()
    return json.dumps([todo.model_dump(mode='json') for todo in todos], indent=2)


@mcp.resource("todos://stats")
def get_stats_resource() -> str:
    """Get todo statistics as a JSON resource."""
    stats = todo_manager.get_stats()
    return json.dumps(stats, indent=2)


@mcp.resource("todos://overdue")
def get_overdue_resource() -> str:
    """Get overdue todos as a JSON resource."""
    overdue = todo_manager.get_overdue_todos()
    return json.dumps([todo.model_dump(mode='json') for todo in overdue], indent=2)


@mcp.resource("todos://categories")
def get_categories_resource() -> str:
    """Get all unique categories."""
    categories = set()
    for todo in todo_manager.todos.values():
        if todo.category:
            categories.add(todo.category)
    return json.dumps(sorted(list(categories)), indent=2)


@mcp.resource("todos://tags")
def get_tags_resource() -> str:
    """Get all unique tags."""
    tags = set()
    for todo in todo_manager.todos.values():
        tags.update(todo.tags)
    return json.dumps(sorted(list(tags)), indent=2)


if __name__ == "__main__":
    # Run the server using STDIO transport (default for Claude Desktop)
    print("Starting FastMCP Todo Server...")
    print("Available at: todos://")
    mcp.run()
