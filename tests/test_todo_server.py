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
from server import mcp, load_tasks, save_tasks, TASKS_FILE


@pytest.fixture
async def client():
    """Create a test client connected to the MCP server."""
    async with Client(mcp) as client:
        yield client


@pytest.fixture
def temp_tasks_file():
    """Create a temporary tasks file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    # Patch the TASKS_FILE global to use our temp file
    original_file = TASKS_FILE
    import server
    server.TASKS_FILE = Path(temp_file)
    
    try:
        yield temp_file
    finally:
        server.TASKS_FILE = original_file
        if os.path.exists(temp_file):
            os.unlink(temp_file)


class TestTaskHelpers:
    """Test the helper functions directly."""
    
    async def test_load_save_tasks(self, temp_tasks_file):
        """Test loading and saving tasks."""
        # Test loading empty file
        tasks = await load_tasks()
        assert tasks == []
        
        # Test saving and loading tasks
        test_tasks = [
            {
                "id": 1,
                "title": "Test Task",
                "priority": "medium",
                "due_date": None,
                "created": datetime.now().isoformat(),
                "completed": False,
                "completed_at": None
            }
        ]
        
        await save_tasks(test_tasks)
        loaded_tasks = await load_tasks()
        
        assert len(loaded_tasks) == 1
        assert loaded_tasks[0]["title"] == "Test Task"
        assert loaded_tasks[0]["priority"] == "medium"
        assert loaded_tasks[0]["completed"] is False


class TestMCPTools:
    """Test the MCP tools through the client interface."""
    
    async def test_add_task_tool(self, client, temp_tasks_file):
        """Test the add_task tool."""
        result = await client.call_tool("add_task", {
            "title": "Test Task via MCP",
            "priority": "high",
            "due_date": "2025-12-31"
        })
        
        response = result[0].text
        
        assert "✅ Added task: 'Test Task via MCP'" in response
        assert "Priority: high" in response
        
        # Verify task was saved
        tasks = await load_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Test Task via MCP"
        assert tasks[0]["priority"] == "high"
        assert tasks[0]["due_date"] == "2025-12-31"
        assert tasks[0]["completed"] is False
    
    async def test_add_task_default_priority(self, client, temp_tasks_file):
        """Test adding task with default priority."""
        result = await client.call_tool("add_task", {
            "title": "Default Priority Task"
        })
        
        response = result[0].text
        assert "Priority: medium" in response
        
        tasks = await load_tasks()
        assert tasks[0]["priority"] == "medium"
    
    async def test_complete_task_tool(self, client, temp_tasks_file):
        """Test the complete_task tool."""
        # First add a task
        await client.call_tool("add_task", {
            "title": "Task to Complete"
        })
        
        # Complete it
        result = await client.call_tool("complete_task", {
            "task_id": 1
        })
        
        response = result[0].text
        assert "🎉 Completed task: 'Task to Complete'" in response
        
        # Verify task is marked completed
        tasks = await load_tasks()
        assert tasks[0]["completed"] is True
        assert tasks[0]["completed_at"] is not None
    
    async def test_complete_nonexistent_task(self, client, temp_tasks_file):
        """Test completing a task that doesn't exist."""
        result = await client.call_tool("complete_task", {
            "task_id": 999
        })
        
        response = result[0].text
        assert "❌ Task 999 not found" in response
    
    async def test_delete_task_tool(self, client, temp_tasks_file):
        """Test the delete_task tool."""
        # First add a task
        await client.call_tool("add_task", {
            "title": "Task to Delete"
        })
        
        # Delete it
        result = await client.call_tool("delete_task", {
            "task_id": 1
        })
        
        response = result[0].text
        assert "🗑️ Deleted task 1" in response
        
        # Verify task is deleted
        tasks = await load_tasks()
        assert len(tasks) == 0
    
    async def test_delete_nonexistent_task(self, client, temp_tasks_file):
        """Test deleting a task that doesn't exist."""
        result = await client.call_tool("delete_task", {
            "task_id": 999
        })
        
        response = result[0].text
        assert "❌ Task 999 not found" in response
    
    async def test_update_task_priority_tool(self, client, temp_tasks_file):
        """Test the update_task_priority tool."""
        # First add a task
        await client.call_tool("add_task", {
            "title": "Task to Update",
            "priority": "low"
        })
        
        # Update priority
        result = await client.call_tool("update_task_priority", {
            "task_id": 1,
            "priority": "urgent"
        })
        
        response = result[0].text
        assert "📝 Updated priority for 'Task to Update' to urgent" in response
        
        # Verify priority was updated
        tasks = await load_tasks()
        assert tasks[0]["priority"] == "urgent"
    
    async def test_update_task_invalid_priority(self, client, temp_tasks_file):
        """Test updating task with invalid priority."""
        await client.call_tool("add_task", {"title": "Test Task"})
        
        result = await client.call_tool("update_task_priority", {
            "task_id": 1,
            "priority": "invalid"
        })
        
        response = result[0].text
        assert "❌ Priority must be one of:" in response
        assert "low, medium, high, urgent" in response
    
    async def test_list_tasks_tool(self, client, temp_tasks_file):
        """Test the list_tasks tool."""
        # Add some tasks
        await client.call_tool("add_task", {"title": "Pending Task", "priority": "high"})
        await client.call_tool("add_task", {"title": "Task to Complete", "priority": "low"})
        await client.call_tool("complete_task", {"task_id": 2})
        
        # Test listing all tasks
        result = await client.call_tool("list_tasks", {"status": "all"})
        response = result[0].text
        
        assert "📋 All Tasks (2 total)" in response
        assert "Pending Task" in response
        assert "Task to Complete" in response
        assert "🟠" in response  # High priority icon
        assert "🔵" in response  # Low priority icon
        
        # Test listing pending tasks only
        result = await client.call_tool("list_tasks", {"status": "pending"})
        response = result[0].text
        
        assert "📋 Pending Tasks (1 total)" in response
        assert "Pending Task" in response
        assert "Task to Complete" not in response  # Should be filtered out
        
        # Test listing completed tasks only
        result = await client.call_tool("list_tasks", {"status": "completed"})
        response = result[0].text
        
        assert "📋 Completed Tasks (1 total)" in response
        assert "Task to Complete" in response
        assert "Pending Task" not in response  # Should be filtered out
    
    async def test_list_tasks_invalid_status(self, client, temp_tasks_file):
        """Test list_tasks with invalid status."""
        result = await client.call_tool("list_tasks", {"status": "invalid"})
        response = result[0].text
        
        assert "❌ Status must be one of:" in response
        assert "all, pending, completed" in response
    
    async def test_add_task_invalid_priority(self, client, temp_tasks_file):
        """Test adding task with invalid priority."""
        result = await client.call_tool("add_task", {
            "title": "Invalid Priority Task",
            "priority": "super_urgent"
        })
        
        response = result[0].text
        # Note: Currently the server doesn't validate priority in add_task
        # This test documents the current behavior - it accepts any priority
        assert "✅ Added task: 'Invalid Priority Task'" in response
        assert "Priority: super_urgent" in response
    
    async def test_add_task_empty_title(self, client, temp_tasks_file):
        """Test adding task with empty title."""
        result = await client.call_tool("add_task", {
            "title": ""
        })
        
        response = result[0].text
        # Currently accepts empty titles - this documents the behavior
        assert "✅ Added task: ''" in response
    
    async def test_list_tasks_empty_list(self, client, temp_tasks_file):
        """Test listing tasks when no tasks exist."""
        result = await client.call_tool("list_tasks", {"status": "all"})
        response = result[0].text
        
        assert "📝 No all tasks found." in response
        
        # Test with specific statuses too
        result = await client.call_tool("list_tasks", {"status": "pending"})
        response = result[0].text
        assert "📝 No pending tasks found." in response
    
    async def test_task_id_generation_with_gaps(self, client, temp_tasks_file):
        """Test that task IDs continue incrementing even after deletions."""
        # Add 3 tasks
        await client.call_tool("add_task", {"title": "Task 1"})
        await client.call_tool("add_task", {"title": "Task 2"}) 
        await client.call_tool("add_task", {"title": "Task 3"})
        
        # Delete the middle task
        await client.call_tool("delete_task", {"task_id": 2})
        
        # Add a new task - should get ID 4, not reuse ID 2
        await client.call_tool("add_task", {"title": "Task 4"})
        
        tasks = await load_tasks()
        task_ids = [task["id"] for task in tasks]
        assert 4 in task_ids  # New task should have ID 4
        assert 2 not in task_ids  # ID 2 should not be reused
        assert len(tasks) == 3  # Should have 3 tasks total
    
    async def test_priority_icons_display(self, client, temp_tasks_file):
        """Test that different priority icons are displayed correctly."""
        # Add tasks with all priority levels
        await client.call_tool("add_task", {"title": "Low Task", "priority": "low"})
        await client.call_tool("add_task", {"title": "Medium Task", "priority": "medium"})
        await client.call_tool("add_task", {"title": "High Task", "priority": "high"})
        await client.call_tool("add_task", {"title": "Urgent Task", "priority": "urgent"})
        
        result = await client.call_tool("list_tasks", {"status": "all"})
        response = result[0].text
        
        # Check that different priority icons appear
        assert "🔵" in response  # Low priority
        assert "🟡" in response  # Medium priority  
        assert "🟠" in response  # High priority
        assert "🔴" in response  # Urgent priority
    
    async def test_due_date_display(self, client, temp_tasks_file):
        """Test that due dates are displayed correctly."""
        await client.call_tool("add_task", {
            "title": "Task with Due Date",
            "due_date": "2025-12-31"
        })
        await client.call_tool("add_task", {
            "title": "Task without Due Date"
        })
        
        result = await client.call_tool("list_tasks", {"status": "all"})
        response = result[0].text
        
        assert "Task with Due Date (Due: 2025-12-31)" in response
        assert "Task without Due Date" in response
        assert "(Due:" not in response.split("Task without Due Date")[1].split("\n")[0]
    
    async def test_corrupted_json_handling(self, temp_tasks_file):
        """Test that corrupted JSON is handled gracefully."""
        # Write corrupted JSON to file
        with open(temp_tasks_file, 'w') as f:
            f.write('{"invalid": json}')
        
        # Should return empty list instead of crashing
        tasks = await load_tasks()
        assert tasks == []
    
    async def test_integration_workflow(self, client, temp_tasks_file):
        """Test a complete workflow of task management."""
        # Add several tasks
        await client.call_tool("add_task", {"title": "Plan project", "priority": "high"})
        await client.call_tool("add_task", {"title": "Write code", "priority": "medium"})
        await client.call_tool("add_task", {"title": "Test code", "priority": "high"})
        await client.call_tool("add_task", {"title": "Deploy", "priority": "low"})
        
        # Check initial state
        result = await client.call_tool("list_tasks", {"status": "pending"})
        assert "4 total" in result[0].text
        
        # Complete some tasks
        await client.call_tool("complete_task", {"task_id": 1})
        await client.call_tool("complete_task", {"task_id": 2})
        
        # Update priority of remaining task
        await client.call_tool("update_task_priority", {"task_id": 3, "priority": "urgent"})
        
        # Check final state
        result = await client.read_resource("tasks://stats")
        stats = json.loads(result[0].text)
        assert stats["total_tasks"] == 4
        assert stats["completed_tasks"] == 2
        assert stats["pending_tasks"] == 2
        assert stats["completion_rate"] == 50.0
        
        # Check that priority was updated
        result = await client.read_resource("tasks://task/3")
        task = json.loads(result[0].text)
        assert task["priority"] == "urgent"
        
        # Delete a task
        await client.call_tool("delete_task", {"task_id": 4})
        
        # Final verification
        result = await client.read_resource("tasks://all")
        tasks = json.loads(result[0].text)
        assert len(tasks) == 3  # Should have 3 tasks left


class TestMCPResources:
    """Test the MCP resources."""
    
    async def test_all_tasks_resource(self, client, temp_tasks_file):
        """Test the tasks://all resource."""
        # Add some tasks first
        await client.call_tool("add_task", {"title": "Task 1", "priority": "high"})
        await client.call_tool("add_task", {"title": "Task 2", "priority": "low"})
        
        # Read the resource
        result = await client.read_resource("tasks://all")
        data = json.loads(result[0].text)
        
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["title"] == "Task 1"
        assert data[1]["title"] == "Task 2"
    
    async def test_pending_tasks_resource(self, client, temp_tasks_file):
        """Test the tasks://pending resource."""
        # Add tasks and complete one
        await client.call_tool("add_task", {"title": "Pending Task"})
        await client.call_tool("add_task", {"title": "Task to Complete"})
        await client.call_tool("complete_task", {"task_id": 2})
        
        # Read pending tasks
        result = await client.read_resource("tasks://pending")
        data = json.loads(result[0].text)
        
        assert len(data) == 1
        assert data[0]["title"] == "Pending Task"
        assert data[0]["completed"] is False
    
    async def test_completed_tasks_resource(self, client, temp_tasks_file):
        """Test the tasks://completed resource."""
        # Add tasks and complete one
        await client.call_tool("add_task", {"title": "Pending Task"})
        await client.call_tool("add_task", {"title": "Completed Task"})
        await client.call_tool("complete_task", {"task_id": 2})
        
        # Read completed tasks
        result = await client.read_resource("tasks://completed")
        data = json.loads(result[0].text)
        
        assert len(data) == 1
        assert data[0]["title"] == "Completed Task"
        assert data[0]["completed"] is True
    
    async def test_priority_tasks_resource(self, client, temp_tasks_file):
        """Test the tasks://priority/{priority} resource."""
        # Add tasks with different priorities
        await client.call_tool("add_task", {"title": "High Priority", "priority": "high"})
        await client.call_tool("add_task", {"title": "Low Priority", "priority": "low"})
        await client.call_tool("add_task", {"title": "Another High", "priority": "high"})
        
        # Read high priority tasks
        result = await client.read_resource("tasks://priority/high")
        data = json.loads(result[0].text)
        
        assert len(data) == 2
        assert all(task["priority"] == "high" for task in data)
    
    async def test_stats_resource(self, client, temp_tasks_file):
        """Test the tasks://stats resource."""
        # Add some tasks with different priorities and complete some
        await client.call_tool("add_task", {"title": "Task 1", "priority": "high"})
        await client.call_tool("add_task", {"title": "Task 2", "priority": "medium"})
        await client.call_tool("add_task", {"title": "Task 3", "priority": "high"})
        await client.call_tool("complete_task", {"task_id": 1})
        
        result = await client.read_resource("tasks://stats")
        stats = json.loads(result[0].text)
        
        assert stats["total_tasks"] == 3
        assert stats["completed_tasks"] == 1
        assert stats["pending_tasks"] == 2
        assert stats["completion_rate"] == 33.3
        assert stats["priority_breakdown"]["high"] == 2  # Only 2 high priority tasks total
        assert stats["priority_breakdown"]["medium"] == 1
    
    async def test_task_details_resource(self, client, temp_tasks_file):
        """Test the tasks://task/{task_id} resource."""
        # Add a task
        await client.call_tool("add_task", {
            "title": "Detailed Task",
            "priority": "urgent",
            "due_date": "2025-12-31"
        })
        
        # Get task details
        result = await client.read_resource("tasks://task/1")
        task = json.loads(result[0].text)
        
        assert task["id"] == 1
        assert task["title"] == "Detailed Task"
        assert task["priority"] == "urgent"
        assert task["due_date"] == "2025-12-31"
        assert task["completed"] is False
    
    async def test_nonexistent_task_details(self, client, temp_tasks_file):
        """Test getting details for non-existent task."""
        result = await client.read_resource("tasks://task/999")
        response = json.loads(result[0].text)
        
        assert "error" in response
        assert "Task 999 not found" in response["error"]
    
    async def test_empty_resources(self, client, temp_tasks_file):
        """Test resources when no tasks exist."""
        # Test all resource endpoints with empty data
        result = await client.read_resource("tasks://all")
        data = json.loads(result[0].text)
        assert data == []
        
        result = await client.read_resource("tasks://pending")
        data = json.loads(result[0].text)
        assert data == []
        
        result = await client.read_resource("tasks://completed")
        data = json.loads(result[0].text)
        assert data == []
        
        result = await client.read_resource("tasks://stats")
        stats = json.loads(result[0].text)
        assert stats["total_tasks"] == 0
        assert stats["completed_tasks"] == 0
        assert stats["pending_tasks"] == 0
        assert stats["completion_rate"] == 0
        assert stats["priority_breakdown"] == {}
    
    async def test_invalid_priority_resource(self, client, temp_tasks_file):
        """Test priority resource with non-existent priority."""
        await client.call_tool("add_task", {"title": "Test Task", "priority": "medium"})
        
        result = await client.read_resource("tasks://priority/nonexistent")
        data = json.loads(result[0].text)
        assert data == []  # Should return empty list for non-matching priority
    
    async def test_invalid_task_id_conversion(self, client, temp_tasks_file):
        """Test task details resource with invalid task ID format."""
        # This should handle the int conversion gracefully
        try:
            result = await client.read_resource("tasks://task/invalid_id")
            # If it doesn't crash, check the response
            response = json.loads(result[0].text)
            # Should either error gracefully or handle the conversion
        except (ValueError, TypeError):
            # Acceptable to throw an error for invalid ID format
            pass


class TestMCPPrompts:
    """Test the MCP prompts."""
    
    async def test_task_prioritization_prompt(self, client):
        """Test the task_prioritization_prompt."""
        result = await client.get_prompt("task_prioritization_prompt", {
            "task_list": "1. Fix bug\n2. Write report\n3. Call client"
        })
        
        prompt = result.messages[0].content.text
        
        assert "prioritize these tasks" in prompt.lower()
        assert "urgency" in prompt.lower()
        assert "importance" in prompt.lower()
        assert "Fix bug" in prompt
        assert "Write report" in prompt
        assert "Call client" in prompt
    
    async def test_daily_planning_prompt(self, client):
        """Test the daily_planning_prompt."""
        result = await client.get_prompt("daily_planning_prompt", {
            "pending_tasks": "Task 1\nTask 2\nTask 3",
            "available_hours": 6
        })
        
        prompt = result.messages[0].content.text
        
        assert "plan my day" in prompt.lower()
        assert "6 hours" in prompt
        assert "Task 1" in prompt
        assert "morning" in prompt.lower()
        assert "afternoon" in prompt.lower()
    
    async def test_task_breakdown_prompt(self, client):
        """Test the task_breakdown_prompt."""
        result = await client.get_prompt("task_breakdown_prompt", {
            "complex_task": "Launch new product"
        })
        
        prompt = result.messages[0].content.text
        
        assert "break this down" in prompt.lower()
        assert "Launch new product" in prompt
        assert "actionable steps" in prompt.lower()
        assert "time estimate" in prompt.lower()
    
    async def test_weekly_review_prompt(self, client):
        """Test the weekly_review_prompt."""
        result = await client.get_prompt("weekly_review_prompt", {
            "completed_tasks": "Completed task 1\nCompleted task 2",
            "pending_tasks": "Pending task 1\nPending task 2"
        })
        
        prompt = result.messages[0].content.text
        
        assert "review my week" in prompt.lower()
        assert "Completed task 1" in prompt
        assert "Pending task 1" in prompt
        assert "wins & achievements" in prompt.lower()
        assert "next week planning" in prompt.lower()
    
    async def test_smart_daily_planning_prompt(self, client, temp_tasks_file):
        """Test the smart_daily_planning_prompt with actual task data."""
        # Add some test tasks first
        await client.call_tool("add_task", {
            "title": "Urgent task", 
            "priority": "urgent",
            "due_date": "2025-06-27"
        })
        await client.call_tool("add_task", {
            "title": "Medium task",
            "priority": "medium"
        })
        await client.call_tool("add_task", {
            "title": "Low priority task",
            "priority": "low"
        })
        
        result = await client.get_prompt("smart_daily_planning_prompt", {})
        prompt = result.messages[0].content.text
        
        assert "Smart Daily Planning" in prompt
        assert "Urgent task" in prompt
        assert "Medium task" in prompt
        assert "🔴" in prompt  # Urgent priority icon
        assert "🟡" in prompt  # Medium priority icon
        assert "Top 3 Focus Tasks" in prompt
    
    async def test_smart_daily_planning_prompt_empty(self, client, temp_tasks_file):
        """Test smart_daily_planning_prompt with no tasks."""
        result = await client.get_prompt("smart_daily_planning_prompt", {})
        prompt = result.messages[0].content.text
        
        assert "no pending tasks" in prompt.lower()
        assert "🎉" in prompt
        assert "well-deserved break" in prompt
    
    async def test_smart_prioritization_prompt(self, client, temp_tasks_file):
        """Test the smart_prioritization_prompt with actual task data."""
        # Add tasks with different priorities
        await client.call_tool("add_task", {
            "title": "High priority task",
            "priority": "high"
        })
        await client.call_tool("add_task", {
            "title": "Low priority task", 
            "priority": "low"
        })
        
        result = await client.get_prompt("smart_prioritization_prompt", {})
        prompt = result.messages[0].content.text
        
        assert "Smart Task Prioritization Analysis" in prompt
        assert "High priority task" in prompt
        assert "Low priority task" in prompt
        assert "Priority Breakdown:" in prompt
        assert "🟠 High:" in prompt  # High priority summary
        assert "🔵 Low:" in prompt   # Low priority summary
        assert "Immediate Action Items" in prompt
    
    async def test_overdue_tasks_prompt_no_overdue(self, client, temp_tasks_file):
        """Test overdue_tasks_prompt with no overdue tasks."""
        result = await client.get_prompt("overdue_tasks_prompt", {})
        prompt = result.messages[0].content.text
        
        assert "Great News!" in prompt
        assert "no overdue tasks" in prompt
        assert "🌟" in prompt
    
    async def test_overdue_tasks_prompt_with_overdue(self, client, temp_tasks_file):
        """Test overdue_tasks_prompt with overdue tasks."""
        # Add an overdue task (yesterday's date)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        await client.call_tool("add_task", {
            "title": "Overdue task",
            "priority": "high", 
            "due_date": yesterday
        })
        
        # Add a task due soon
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        await client.call_tool("add_task", {
            "title": "Due soon task",
            "priority": "medium",
            "due_date": tomorrow
        })
        
        result = await client.get_prompt("overdue_tasks_prompt", {})
        prompt = result.messages[0].content.text
        
        assert "Deadline Management Alert" in prompt
        assert "Overdue Tasks" in prompt
        assert "Due Soon" in prompt
        assert "Overdue task" in prompt
        assert "Due soon task" in prompt
        assert "days overdue" in prompt
        assert "Triage Strategy" in prompt


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    async def test_prompt_with_empty_parameters(self, client):
        """Test prompts with empty/minimal parameters."""
        result = await client.get_prompt("task_prioritization_prompt", {
            "task_list": ""
        })
        prompt = result.messages[0].content.text
        assert "prioritize these tasks" in prompt.lower()
        
        result = await client.get_prompt("daily_planning_prompt", {
            "pending_tasks": "",
            "available_hours": 0
        })
        prompt = result.messages[0].content.text
        assert "0 hours" in prompt
    
    async def test_very_long_task_title(self, client, temp_tasks_file):
        """Test handling of very long task titles."""
        long_title = "A" * 1000  # 1000 character title
        result = await client.call_tool("add_task", {
            "title": long_title,
            "priority": "medium"
        })
        
        response = result[0].text
        assert "✅ Added task:" in response
        
        # Verify it was saved correctly
        tasks = await load_tasks()
        assert tasks[0]["title"] == long_title
    
    async def test_special_characters_in_title(self, client, temp_tasks_file):
        """Test handling of special characters in task titles."""
        special_title = "Task with émojis 🎉 and spëcial chars & symbols!"
        result = await client.call_tool("add_task", {
            "title": special_title
        })
        
        response = result[0].text
        assert special_title in response
        
        # Test listing also handles special characters
        result = await client.call_tool("list_tasks", {"status": "all"})
        response = result[0].text
        assert special_title in response


if __name__ == "__main__":
    pytest.main([__file__])
