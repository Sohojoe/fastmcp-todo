"""
Test suite for the FastMCP Todo Server.
"""

import asyncio
import pytest
import json
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastmcp import Client
from server import mcp, TodoManager, Priority, Status


@pytest.fixture
async def client():
    """Create a test client connected to the MCP server."""
    async with Client(mcp) as client:
        yield client


@pytest.fixture
def temp_todo_manager():
    """Create a temporary todo manager for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        manager = TodoManager(temp_file)
        yield manager
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


class TestTodoManager:
    """Test the TodoManager class directly."""
    
    def test_create_todo(self, temp_todo_manager):
        """Test creating a new todo."""
        todo = temp_todo_manager.create_todo(
            title="Test Todo",
            description="A test todo",
            priority=Priority.HIGH,
            category="test"
        )
        
        assert todo.id == 1
        assert todo.title == "Test Todo"
        assert todo.description == "A test todo"
        assert todo.priority == Priority.HIGH
        assert todo.status == Status.TODO
        assert todo.category == "test"
        assert todo.created_at is not None
        assert todo.updated_at is not None
    
    def test_get_todo(self, temp_todo_manager):
        """Test getting a todo by ID."""
        todo = temp_todo_manager.create_todo("Test Todo")
        retrieved = temp_todo_manager.get_todo(1)
        
        assert retrieved is not None
        assert retrieved.id == 1
        assert retrieved.title == "Test Todo"
        
        # Test getting non-existent todo
        assert temp_todo_manager.get_todo(999) is None
    
    def test_update_todo(self, temp_todo_manager):
        """Test updating a todo."""
        todo = temp_todo_manager.create_todo("Original Title")
        
        updated = temp_todo_manager.update_todo(
            1,
            title="Updated Title",
            priority=Priority.URGENT,
            status=Status.IN_PROGRESS
        )
        
        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.priority == Priority.URGENT
        assert updated.status == Status.IN_PROGRESS
        assert updated.updated_at > updated.created_at
    
    def test_delete_todo(self, temp_todo_manager):
        """Test deleting a todo."""
        temp_todo_manager.create_todo("To Delete")
        
        assert temp_todo_manager.delete_todo(1) is True
        assert temp_todo_manager.get_todo(1) is None
        assert temp_todo_manager.delete_todo(999) is False
    
    def test_list_todos_with_filters(self, temp_todo_manager):
        """Test listing todos with various filters."""
        # Create test todos
        temp_todo_manager.create_todo("Todo 1", priority=Priority.HIGH, category="work")
        temp_todo_manager.create_todo("Todo 2", priority=Priority.LOW, category="personal")
        temp_todo_manager.update_todo(2, status=Status.COMPLETED)
        temp_todo_manager.create_todo("Todo 3", priority=Priority.HIGH, category="work")
        
        # Test no filters
        all_todos = temp_todo_manager.list_todos()
        assert len(all_todos) == 3
        
        # Test status filter
        completed = temp_todo_manager.list_todos(status=Status.COMPLETED)
        assert len(completed) == 1
        assert completed[0].title == "Todo 2"
        
        # Test category filter
        work_todos = temp_todo_manager.list_todos(category="work")
        assert len(work_todos) == 2
        
        # Test priority filter
        high_priority = temp_todo_manager.list_todos(priority=Priority.HIGH)
        assert len(high_priority) == 2
    
    def test_get_stats(self, temp_todo_manager):
        """Test getting todo statistics."""
        # Create test data
        temp_todo_manager.create_todo("Todo 1", category="work")
        temp_todo_manager.create_todo("Todo 2", category="work")
        temp_todo_manager.create_todo("Todo 3", category="personal")
        temp_todo_manager.update_todo(2, status=Status.COMPLETED)
        
        stats = temp_todo_manager.get_stats()
        
        assert stats['total'] == 3
        assert stats['completed'] == 1
        assert stats['pending'] == 2
        assert stats['completion_rate'] == 33.3
        assert stats['by_category']['work'] == 1  # Only non-completed work todos
        assert stats['by_category']['personal'] == 1
    
    def test_overdue_todos(self, temp_todo_manager):
        """Test getting overdue todos."""
        # Create todos with different due dates
        past_date = datetime.now() - timedelta(days=1)
        future_date = datetime.now() + timedelta(days=1)
        
        temp_todo_manager.create_todo("Overdue", due_date=past_date)
        temp_todo_manager.create_todo("Not Overdue", due_date=future_date)
        temp_todo_manager.create_todo("Overdue but Completed", due_date=past_date)
        temp_todo_manager.update_todo(3, status=Status.COMPLETED)
        
        overdue = temp_todo_manager.get_overdue_todos()
        assert len(overdue) == 1
        assert overdue[0].title == "Overdue"


class TestMCPTools:
    """Test the MCP tools through the client interface."""
    
    async def test_create_todo_tool(self, client):
        """Test the create_todo tool."""
        result = await client.call_tool("create_todo", {
            "title": "Test via MCP",
            "description": "Testing MCP tool",
            "priority": "high",
            "category": "test",
            "tags": "mcp,testing"
        })
        
        response = result[0].text
        data = json.loads(response)
        
        assert data["success"] is True
        assert "todo" in data
        assert data["todo"]["title"] == "Test via MCP"
        assert data["todo"]["priority"] == "high"
        assert data["todo"]["category"] == "test"
        assert "mcp" in data["todo"]["tags"]
        assert "testing" in data["todo"]["tags"]
    
    async def test_list_todos_tool(self, client):
        """Test the list_todos tool."""
        # First create some todos
        await client.call_tool("create_todo", {
            "title": "Todo 1",
            "priority": "high",
            "category": "work"
        })
        await client.call_tool("create_todo", {
            "title": "Todo 2", 
            "priority": "low",
            "category": "personal"
        })
        
        # List all todos
        result = await client.call_tool("list_todos", {})
        response = result[0].text
        data = json.loads(response)
        
        assert data["success"] is True
        assert len(data["todos"]) >= 2
        assert data["total_count"] >= 2
    
    async def test_search_todos_tool(self, client):
        """Test the search_todos tool."""
        # Create a todo to search for
        await client.call_tool("create_todo", {
            "title": "Searchable Todo",
            "description": "This todo contains searchable content"
        })
        
        # Search for it
        result = await client.call_tool("search_todos", {
            "query": "searchable",
            "limit": 10
        })
        
        response = result[0].text
        data = json.loads(response)
        
        assert data["success"] is True
        assert data["total_matches"] >= 1
        assert any("searchable" in todo["title"].lower() or 
                 "searchable" in (todo["description"] or "").lower() 
                 for todo in data["todos"])
    
    async def test_complete_todo_tool(self, client):
        """Test the complete_todo tool."""
        # Create a todo first
        create_result = await client.call_tool("create_todo", {
            "title": "Todo to Complete"
        })
        create_data = json.loads(create_result[0].text)
        todo_id = create_data["todo"]["id"]
        
        # Complete it
        result = await client.call_tool("complete_todo", {
            "todo_id": todo_id
        })
        
        response = result[0].text
        data = json.loads(response)
        
        assert data["success"] is True
        assert data["todo"]["status"] == "completed"
    
    async def test_get_todo_stats_tool(self, client):
        """Test the get_todo_stats tool."""
        result = await client.call_tool("get_todo_stats", {})
        response = result[0].text
        data = json.loads(response)
        
        assert data["success"] is True
        assert "statistics" in data
        stats = data["statistics"]
        assert "total" in stats
        assert "completed" in stats
        assert "pending" in stats
        assert "completion_rate" in stats
    
    async def test_invalid_priority(self, client):
        """Test creating todo with invalid priority."""
        result = await client.call_tool("create_todo", {
            "title": "Invalid Priority Todo",
            "priority": "invalid_priority"
        })
        
        response = result[0].text
        data = json.loads(response)
        
        assert "error" in data
        assert "invalid priority" in data["error"].lower()
    
    async def test_invalid_date_format(self, client):
        """Test creating todo with invalid date format."""
        result = await client.call_tool("create_todo", {
            "title": "Invalid Date Todo",
            "due_date": "not-a-date"
        })
        
        response = result[0].text
        data = json.loads(response)
        
        assert "error" in data
        assert "date" in data["error"].lower()


class TestMCPResources:
    """Test the MCP resources."""
    
    async def test_all_todos_resource(self, client):
        """Test the todos://all resource."""
        # Create a todo first
        await client.call_tool("create_todo", {"title": "Resource Test Todo"})
        
        # Read the resource
        result = await client.read_resource("todos://all")
        data = json.loads(result[0].text)
        
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(todo["title"] == "Resource Test Todo" for todo in data)
    
    async def test_stats_resource(self, client):
        """Test the todos://stats resource."""
        result = await client.read_resource("todos://stats")
        stats = json.loads(result[0].text)
        
        assert "total" in stats
        assert "completed" in stats
        assert "pending" in stats
        assert "completion_rate" in stats
    
    async def test_categories_resource(self, client):
        """Test the todos://categories resource."""
        # Create todos with categories
        await client.call_tool("create_todo", {
            "title": "Work Todo", 
            "category": "work"
        })
        await client.call_tool("create_todo", {
            "title": "Personal Todo",
            "category": "personal"
        })
        
        result = await client.read_resource("todos://categories")
        categories = json.loads(result[0].text)
        
        assert isinstance(categories, list)
        assert "work" in categories
        assert "personal" in categories
    
    async def test_tags_resource(self, client):
        """Test the todos://tags resource."""
        # Create todos with tags
        await client.call_tool("create_todo", {
            "title": "Tagged Todo",
            "tags": "important,urgent,work"
        })
        
        result = await client.read_resource("todos://tags")
        tags = json.loads(result[0].text)
        
        assert isinstance(tags, list)
        assert "important" in tags
        assert "urgent" in tags
        assert "work" in tags


if __name__ == "__main__":
    pytest.main([__file__])
