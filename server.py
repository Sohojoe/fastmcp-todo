#!/usr/bin/env python3
"""
Complete Todo MCP Server with PostgreSQL support
Demonstrates all 3 MCP endpoint types: Tools, Resources, and Prompts
Uses PostgreSQL when available (Railway), falls back to file storage locally
"""
import os
import sys
import uvicorn
from fastmcp import FastMCP
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio
from dotenv import load_dotenv
from storage import StorageStrategy, StorageFactory

# Load environment variables from .env file
load_dotenv()

mcp = FastMCP("complete-todo-server")

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway provides this
TABLE_NAME = os.getenv("TABLE_NAME", "tasks")  # Configurable table name
TASKS_FILE = os.getenv("TASKS_FILE", "tasks.json")  # Configurable file path

# Global storage strategy
storage: Optional[StorageStrategy] = None

# =============================================================================
# STORAGE INITIALIZATION
# =============================================================================

async def init_storage():
    """Initialize storage strategy."""
    global storage
    if storage is None:
        storage = StorageFactory.create_storage(
            database_url=DATABASE_URL,
            file_path=TASKS_FILE,
            table_name=TABLE_NAME
        )
        await storage.initialize()

async def close_storage():
    """Close storage connections."""
    global storage
    if storage:
        await storage.close()
        storage = None

def reset_storage_state():
    """Reset storage state for testing."""
    global storage
    storage = None

# =============================================================================
# STORAGE WRAPPER FUNCTIONS
# =============================================================================

async def load_tasks() -> List[Dict[str, Any]]:
    """Load all tasks using the storage strategy."""
    await init_storage()
    return await storage.get_all_tasks()

async def add_task_to_storage(title: str, priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
    """Add task using the storage strategy."""
    await init_storage()
    return await storage.add_task(title, priority, due_date)

async def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    """Get task by ID using the storage strategy."""
    await init_storage()
    return await storage.get_task_by_id(task_id)

async def update_task_completion(task_id: int, completed: bool) -> bool:
    """Update task completion using the storage strategy."""
    await init_storage()
    return await storage.update_task_completed(task_id, completed)

async def delete_task_from_storage(task_id: int) -> bool:
    """Delete task using the storage strategy."""
    await init_storage()
    return await storage.delete_task(task_id)

async def update_task_priority_in_storage(task_id: int, priority: str) -> bool:
    """Update task priority using the storage strategy."""
    await init_storage()
    return await storage.update_task_priority(task_id, priority)

# =============================================================================
# TOOLS (Actions - like POST endpoints)
# =============================================================================

@mcp.tool()
async def add_task(title: str, priority: str = "medium", due_date: Optional[str] = None) -> str:
    """Add a new task to the todo list."""
    task = await add_task_to_storage(title, priority, due_date)
    return f"✅ Added task: '{title}' (Priority: {priority}) [ID: {task['id']}]"

@mcp.tool()
async def complete_task(task_id: int) -> str:
    """Mark a task as completed."""
    # Get task details first
    task = await get_task_by_id(task_id)
    if not task:
        return f"❌ Task {task_id} not found"
    
    success = await update_task_completion(task_id, True)
    if success:
        return f"🎉 Completed task: '{task['title']}'"
    return f"❌ Failed to complete task {task_id}"

@mcp.tool()
async def delete_task(task_id: int) -> str:
    """Delete a task from the todo list."""
    success = await delete_task_from_storage(task_id)
    if success:
        return f"🗑️ Deleted task {task_id}"
    return f"❌ Task {task_id} not found"

@mcp.tool()
async def update_task_priority(task_id: int, priority: str) -> str:
    """Update the priority of a task."""
    valid_priorities = ["low", "medium", "high", "urgent"]
    if priority not in valid_priorities:
        return f"❌ Priority must be one of: {', '.join(valid_priorities)}"
    
    # Get task details first
    task = await get_task_by_id(task_id)
    if not task:
        return f"❌ Task {task_id} not found"
    
    success = await update_task_priority_in_storage(task_id, priority)
    if success:
        return f"📝 Updated priority for '{task['title']}' to {priority}"
    return f"❌ Failed to update task {task_id}"

@mcp.tool()
async def list_tasks(status: str = "all") -> str:
    """List tasks with optional status filter."""
    valid_statuses = ["all", "pending", "completed"]
    if status not in valid_statuses:
        return f"❌ Status must be one of: {', '.join(valid_statuses)}"
    
    tasks = await load_tasks()
    
    if status == "pending":
        tasks = [task for task in tasks if not task["completed"]]
    elif status == "completed":
        tasks = [task for task in tasks if task["completed"]]
    
    if not tasks:
        return f"📝 No {status} tasks found."
    
    # Format tasks for display
    task_lines = []
    for task in tasks:
        status_icon = "✅" if task["completed"] else "⏳"
        priority_icon = {"low": "🔵", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(task["priority"], "⚪")
        
        line = f"{status_icon} {priority_icon} [{task['id']}] {task['title']}"
        if task["due_date"]:
            line += f" (Due: {task['due_date']})"
        task_lines.append(line)
    
    await init_storage()
    storage_type = storage.get_storage_type()
    header = f"📋 {status.title()} Tasks ({len(tasks)} total) [{storage_type}]:\n"
    return header + "\n".join(task_lines)

# =============================================================================
# RESOURCES (Data - like GET endpoints)
# =============================================================================

@mcp.resource("tasks://all")
async def get_all_tasks() -> list:
    """Get all tasks in the todo list."""
    return await load_tasks()

@mcp.resource("tasks://pending")
async def get_pending_tasks() -> list:
    """Get all uncompleted tasks."""
    tasks = await load_tasks()
    return [task for task in tasks if not task["completed"]]

@mcp.resource("tasks://completed")
async def get_completed_tasks() -> list:
    """Get all completed tasks."""
    tasks = await load_tasks()
    return [task for task in tasks if task["completed"]]

@mcp.resource("tasks://priority/{priority}")
async def get_tasks_by_priority(priority: str) -> list:
    """Get tasks filtered by priority level."""
    tasks = await load_tasks()
    return [task for task in tasks if task["priority"] == priority]

@mcp.resource("tasks://stats")
async def get_task_statistics() -> dict:
    """Get statistics about tasks."""
    tasks = await load_tasks()
    total = len(tasks)
    completed = len([t for t in tasks if t["completed"]])
    pending = total - completed
    
    priority_counts = {}
    for task in tasks:
        priority = task["priority"]
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
    
    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "pending_tasks": pending,
        "completion_rate": round((completed / total * 100) if total > 0 else 0, 1),
        "priority_breakdown": priority_counts,
        "storage_type": storage.get_storage_type() if storage else "Unknown"
    }

@mcp.resource("tasks://task/{task_id}")
async def get_task_details(task_id: str) -> dict:
    """Get detailed information about a specific task."""
    # Handle invalid task ID format gracefully
    try:
        task_id_int = int(task_id)
    except ValueError:
        return {"error": f"Invalid task ID format: '{task_id}'. Task ID must be a number."}
    
    task = await get_task_by_id(task_id_int)
    if task:
        return task
    
    return {"error": f"Task {task_id} not found"}

# =============================================================================
# PROMPTS (Templates - reusable prompt patterns)
# =============================================================================

@mcp.prompt()
def task_prioritization_prompt(task_list: str) -> str:
    """Generate a prompt for AI to help prioritize tasks."""
    return f"""
Please help me prioritize these tasks based on urgency and importance:

{task_list}

For each task, consider:
1. **Urgency**: How time-sensitive is this task?
2. **Importance**: How critical is this to my goals?
3. **Effort**: How much time/energy will this take?
4. **Dependencies**: Does this block other tasks?

Please provide:
- A prioritized list (most important first)
- Brief reasoning for the top 3 priorities
- Suggestions for which tasks could be delegated or eliminated

Use this format:
## Priority Order
1. [Task] - [Reason]
2. [Task] - [Reason]
...

## Recommendations
- **Focus on**: [top priorities]
- **Delegate**: [tasks that could be delegated]
- **Eliminate**: [tasks that aren't necessary]
"""

@mcp.prompt()
def daily_planning_prompt(pending_tasks: str, available_hours: int = 8) -> str:
    """Generate a prompt for daily task planning."""
    return f"""
Help me plan my day with these pending tasks:

{pending_tasks}

I have approximately {available_hours} hours available today.

Please suggest:
1. **Today's Focus**: Which 3-5 tasks should I prioritize today?
2. **Time Blocking**: Rough time estimates for each task
3. **Quick Wins**: Any tasks I can knock out in <30 minutes
4. **Tomorrow's Prep**: Tasks to defer to tomorrow

Consider energy levels throughout the day:
- Morning (high energy): Complex/creative work
- Afternoon (medium energy): Meetings/communication
- Evening (low energy): Admin/routine tasks

Format your response as a structured daily plan.
"""

@mcp.prompt()
def task_breakdown_prompt(complex_task: str) -> str:
    """Generate a prompt to break down a complex task into smaller steps."""
    return f"""
This task feels overwhelming to me:
"{complex_task}"

Please help me break this down into manageable, actionable steps.

For each step, provide:
- **Action**: Clear, specific action to take
- **Time Estimate**: Rough time needed
- **Resources**: What I'll need to complete it
- **Success Criteria**: How I'll know it's done

Make each step small enough that I could complete it in one focused session (1-2 hours max).

Also suggest:
- Which steps could be done in parallel
- Which steps are blockers for others
- Any steps that could be simplified or eliminated

Please format as a numbered checklist I can follow.
"""

@mcp.prompt()
def weekly_review_prompt(completed_tasks: str, pending_tasks: str) -> str:
    """Generate a prompt for weekly productivity review."""
    return f"""
Help me review my week and plan ahead.

## What I Completed This Week:
{completed_tasks}

## What's Still Pending:
{pending_tasks}

Please help me analyze:

### 🎉 **Wins & Achievements**
- What went well this week?
- Which accomplishments should I celebrate?
- What patterns led to success?

### 🔍 **Learning & Improvement**
- What tasks took longer than expected? Why?
- Which tasks got delayed or avoided? What were the blockers?
- What would I do differently?

### 📅 **Next Week Planning**
- Which pending tasks are most critical for next week?
- What new priorities should I consider?
- How can I build on this week's momentum?

### ⚡ **Optimization**
- Are there any recurring tasks I could automate or streamline?
- What tools or processes would help me be more efficient?

Please provide specific, actionable insights to help me improve my productivity.
"""

@mcp.prompt()
async def smart_daily_planning_prompt() -> str:
    """Generate a smart daily planning prompt using actual task data."""
    tasks = await load_tasks()
    pending_tasks = [task for task in tasks if not task["completed"]]
    
    if not pending_tasks:
        return """
You currently have no pending tasks! 🎉

This might be a good time to:
- Review your completed work and celebrate achievements
- Plan new goals or projects
- Take a well-deserved break
- Reflect on your productivity systems

Consider adding some new tasks or reviewing your weekly/monthly objectives.
"""
    
    # Sort by priority and due date
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    pending_tasks.sort(key=lambda t: (
        priority_order.get(t["priority"], 4),
        t["due_date"] is None,  # Tasks with due dates first
        t["due_date"] or ""
    ))
    
    task_list = []
    for task in pending_tasks:
        priority_icon = {"low": "🔵", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(task["priority"], "⚪")
        due_info = f" (Due: {task['due_date']})" if task["due_date"] else ""
        task_list.append(f"{priority_icon} [{task['id']}] {task['title']}{due_info}")
    
    tasks_text = "\n".join(task_list)
    await init_storage()
    storage_type = storage.get_storage_type()
    
    return f"""
📅 **Smart Daily Planning** [{storage_type} Storage]

Here are your pending tasks, sorted by priority and due date:

{tasks_text}

**AI Assistant Instructions:**
Please help me plan my day with these tasks. Consider:

1. **Urgent/Overdue Items**: Prioritize anything urgent or with approaching due dates
2. **Energy Matching**: Match high-priority/complex tasks to my peak energy times
3. **Realistic Scheduling**: I typically have 6-8 productive hours per day
4. **Balance**: Mix high-effort tasks with easier "quick wins"

Please provide:
- **Top 3 Focus Tasks** for today (with reasons)
- **Quick Wins** (tasks that take <30 minutes)
- **Time Blocking** suggestion for the day
- **Defer to Tomorrow** (tasks to postpone if needed)

Consider that I'm most productive in the morning for complex work, and afternoons are better for communication/admin tasks.
"""

@mcp.prompt()
async def smart_prioritization_prompt() -> str:
    """Generate a smart prioritization prompt using actual task data and statistics."""
    tasks = await load_tasks()
    pending_tasks = [task for task in tasks if not task["completed"]]
    
    if not pending_tasks:
        return "You have no pending tasks to prioritize! Consider adding some new tasks or goals."
    
    # Get statistics directly
    total_tasks = len(tasks)
    completed_tasks = len([t for t in tasks if t["completed"]])
    completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)
    total_pending = len(pending_tasks)
    
    # Group by priority
    by_priority = {}
    for task in pending_tasks:
        priority = task["priority"]
        if priority not in by_priority:
            by_priority[priority] = []
        by_priority[priority].append(task)
    
    priority_summary = []
    for priority in ["urgent", "high", "medium", "low"]:
        if priority in by_priority:
            count = len(by_priority[priority])
            icon = {"low": "🔵", "medium": "🟡", "high": "🟠", "urgent": "🔴"}[priority]
            priority_summary.append(f"{icon} {priority.title()}: {count} tasks")
    
    # Format task list with details
    task_details = []
    for task in pending_tasks:
        priority_icon = {"low": "🔵", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(task["priority"], "⚪")
        due_info = f" | Due: {task['due_date']}" if task["due_date"] else ""
        # Handle both string and datetime created fields
        created_str = task["created"]
        if hasattr(created_str, 'isoformat'):
            created_str = created_str.isoformat()
        created_date = created_str[:10] if created_str else "Unknown"
        task_details.append(f"{priority_icon} [{task['id']}] {task['title']} | Priority: {task['priority']}{due_info} | Created: {created_date}")
    
    tasks_text = "\n".join(task_details)
    priority_text = "\n".join(priority_summary)
    await init_storage()
    storage_type = storage.get_storage_type()
    
    return f"""
🎯 **Smart Task Prioritization Analysis** [{storage_type} Storage]

**Current Task Overview:**
- Total pending tasks: {total_pending}
- Completion rate: {completion_rate}%

**Priority Breakdown:**
{priority_text}

**All Pending Tasks:**
{tasks_text}

**AI Assistant Instructions:**
Please analyze my task list and help me prioritize more effectively. Consider:

1. **Priority Alignment**: Are my current priority levels appropriate?
2. **Due Date Urgency**: Which tasks need immediate attention based on deadlines?
3. **Workload Balance**: Do I have too many high-priority items?
4. **Task Dependencies**: Which tasks might be blockers for others?
5. **Energy Requirements**: Which tasks need high focus vs. routine work?

Please provide:
- **Immediate Action Items** (must do today/this week)
- **Priority Adjustments** (tasks that should be re-prioritized)
- **Consolidation Opportunities** (tasks that could be combined)
- **Elimination Candidates** (tasks that might not be necessary)
- **Strategic Recommendations** for better task management

Focus on actionable insights that will improve my productivity and reduce overwhelm.
"""

@mcp.prompt()
async def overdue_tasks_prompt() -> str:
    """Generate a prompt for handling overdue tasks."""
    tasks = await load_tasks()
    today = datetime.now().date()
    
    overdue_tasks = []
    upcoming_tasks = []
    
    for task in tasks:
        if not task["completed"] and task["due_date"]:
            try:
                due_date = datetime.fromisoformat(task["due_date"]).date()
                if due_date < today:
                    overdue_tasks.append(task)
                elif due_date <= today + timedelta(days=3):  # Next 3 days
                    upcoming_tasks.append(task)
            except (ValueError, TypeError):
                continue  # Skip invalid dates
    
    if not overdue_tasks and not upcoming_tasks:
        await init_storage()
        storage_type = storage.get_storage_type()
        return f"""
🌟 **Great News!** [{storage_type} Storage]

You have no overdue tasks and nothing urgent coming up in the next few days!

This is a good time to:
- Focus on medium/long-term goals
- Work on high-impact but non-urgent tasks
- Plan ahead for future deadlines
- Take on new challenges or learning opportunities

Keep up the excellent time management! 
"""
    
    await init_storage()
    storage_type = storage.get_storage_type()
    content = f"⚠️ **Deadline Management Alert** [{storage_type} Storage]\n\n"
    
    if overdue_tasks:
        content += f"**🚨 Overdue Tasks ({len(overdue_tasks)}):**\n"
        for task in overdue_tasks:
            days_overdue = (today - datetime.fromisoformat(task["due_date"]).date()).days
            priority_icon = {"low": "🔵", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(task["priority"], "⚪")
            content += f"{priority_icon} [{task['id']}] {task['title']} - {days_overdue} days overdue\n"
        content += "\n"
    
    if upcoming_tasks:
        content += f"**⏰ Due Soon ({len(upcoming_tasks)}):**\n"
        for task in upcoming_tasks:
            due_date = datetime.fromisoformat(task["due_date"]).date()
            days_until = (due_date - today).days
            due_text = "Today" if days_until == 0 else f"{days_until} days"
            priority_icon = {"low": "🔵", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(task["priority"], "⚪")
            content += f"{priority_icon} [{task['id']}] {task['title']} - Due in {due_text}\n"
        content += "\n"
    
    content += """**AI Assistant Instructions:**
Please help me create an action plan for these deadline-sensitive tasks:

1. **Triage Strategy**: Which overdue tasks are still worth completing vs. which should be cancelled/rescheduled?
2. **Immediate Actions**: What should I tackle first today?
3. **Time Blocking**: How should I allocate time to catch up?
4. **Prevention**: How can I avoid this situation in the future?
5. **Communication**: Do I need to notify anyone about delays?

Please provide a clear, actionable plan that helps me regain control of my deadlines while being realistic about what's achievable.
"""
    
    return content

# =============================================================================
# STARTUP AND CLEANUP
# =============================================================================

async def startup():
    """Initialize the application."""
    await init_storage()

async def cleanup():
    """Clean up resources."""
    try:
        await close_storage()
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    is_deployment = os.getenv("PORT") is not None or os.getenv("RAILWAY_ENVIRONMENT") is not None
    is_stdio_mode = not sys.stdin.isatty() and not is_deployment
    
    if is_stdio_mode:
        # Run in stdio mode for local MCP clients

        async def run_server():
            await startup()
            try:
                await mcp.run_stdio_async()
            finally:
                await cleanup()
        
        asyncio.run(run_server())   

    else:
        # Simple approach: run on root path
        print(f"Running MCP HTTP server on port {port}")
        async def run_server():
            await startup()
            try:
                await mcp.run_http_async(
                    host="0.0.0.0",
                    port=port,
                    path="/",
                    log_level="debug"
                )
            finally:
                await cleanup()
        
        asyncio.run(run_server())      
