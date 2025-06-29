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
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import asyncio
import asyncpg
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

mcp = FastMCP("complete-todo-server")

# Configuration
TASKS_FILE = Path("tasks.json")
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway provides this
USE_DATABASE = DATABASE_URL is not None

# Global database connection pool
db_pool = None
_db_initialized = False

# =============================================================================
# DATABASE SETUP AND ABSTRACTIONS
# =============================================================================

async def init_database():
    """Initialize database connection and create tables if needed."""
    global db_pool, USE_DATABASE, _db_initialized
    
    if _db_initialized:
        return
    
    if not USE_DATABASE:
        print("📁 Using file-based storage (tasks.json)")
        _db_initialized = True
        return
    
    try:
        print("🐘 Connecting to PostgreSQL...")
        # Create connection pool with more conservative settings for tests
        db_pool = await asyncpg.create_pool(
            DATABASE_URL, 
            min_size=1, 
            max_size=5,
            command_timeout=5,
            server_settings={
                'application_name': 'fastmcp_todo'
            }
        )
        
        # Test the connection and create tasks table if it doesn't exist
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'medium',
                    due_date TEXT,
                    created TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    completed BOOLEAN NOT NULL DEFAULT FALSE,
                    completed_at TIMESTAMP WITH TIME ZONE
                )
            """)
        print("✅ PostgreSQL connected and initialized")
        _db_initialized = True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("📁 Falling back to file-based storage")
        # Clean up any partial pool
        if db_pool:
            try:
                await db_pool.close()
            except:
                pass
            db_pool = None
        USE_DATABASE = False
        _db_initialized = True

async def ensure_db_initialized():
    """Ensure database is initialized before performing operations."""
    if not _db_initialized:
        await init_database()

async def close_database():
    """Close database connections."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None

def reset_database_state():
    """Reset database state for testing."""
    global _db_initialized, db_pool, USE_DATABASE
    _db_initialized = False
    if db_pool:
        # Note: This should only be called when the event loop is about to be cleaned up
        db_pool = None
    # Reset USE_DATABASE to its original value
    USE_DATABASE = DATABASE_URL is not None

# Database operations
async def db_add_task(title: str, priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
    """Add task to database."""
    await ensure_db_initialized()
    assert db_pool is not None  # Only called when USE_DATABASE is True
    async with db_pool.acquire() as conn:
        task_id = await conn.fetchval("""
            INSERT INTO tasks (title, priority, due_date)
            VALUES ($1, $2, $3)
            RETURNING id
        """, title, priority, due_date)
        
        # Return the full task
        return await conn.fetchrow("""
            SELECT id, title, priority, due_date, created, completed, completed_at
            FROM tasks WHERE id = $1
        """, task_id)

async def db_get_all_tasks() -> List[Dict[str, Any]]:
    """Get all tasks from database."""
    await ensure_db_initialized()
    assert db_pool is not None  # Only called when USE_DATABASE is True
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, title, priority, due_date, created, completed, completed_at
            FROM tasks
            ORDER BY id
        """)
        return [dict(row) for row in rows]

async def db_update_task_completed(task_id: int, completed: bool) -> bool:
    """Update task completion status."""
    await ensure_db_initialized()
    assert db_pool is not None  # Only called when USE_DATABASE is True
    async with db_pool.acquire() as conn:
        completed_at = datetime.now() if completed else None
        result = await conn.execute("""
            UPDATE tasks 
            SET completed = $1, completed_at = $2
            WHERE id = $3
        """, completed, completed_at, task_id)
        return result != "UPDATE 0"

async def db_delete_task(task_id: int) -> bool:
    """Delete task from database."""
    await ensure_db_initialized()
    assert db_pool is not None  # Only called when USE_DATABASE is True
    async with db_pool.acquire() as conn:
        result = await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
        return result != "DELETE 0"

async def db_update_task_priority(task_id: int, priority: str) -> bool:
    """Update task priority."""
    await ensure_db_initialized()
    assert db_pool is not None  # Only called when USE_DATABASE is True
    async with db_pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE tasks SET priority = $1 WHERE id = $2
        """, priority, task_id)
        return result != "UPDATE 0"

async def db_get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    """Get specific task by ID."""
    await ensure_db_initialized()
    assert db_pool is not None  # Only called when USE_DATABASE is True
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, title, priority, due_date, created, completed, completed_at
            FROM tasks WHERE id = $1
        """, task_id)
        return dict(row) if row else None

# =============================================================================
# UNIFIED DATA ACCESS LAYER
# =============================================================================

def format_task_for_json(task: Dict[str, Any]) -> Dict[str, Any]:
    """Convert database task to JSON-compatible format."""
    if not USE_DATABASE:
        return task
    
    # Convert datetime objects to ISO strings
    formatted_task = task.copy()
    if task.get('created') and hasattr(task['created'], 'isoformat'):
        formatted_task['created'] = task['created'].isoformat()
    if task.get('completed_at') and hasattr(task['completed_at'], 'isoformat'):
        formatted_task['completed_at'] = task['completed_at'].isoformat()
    
    return formatted_task

async def load_tasks() -> List[Dict[str, Any]]:
    """Load tasks from database or file."""
    if USE_DATABASE:
        tasks = await db_get_all_tasks()
        return [format_task_for_json(task) for task in tasks]
    else:
        # File-based fallback
        if TASKS_FILE.exists():
            try:
                return json.loads(TASKS_FILE.read_text())
            except json.JSONDecodeError:
                return []
        return []

async def save_tasks(tasks: List[Dict[str, Any]]):
    """Save tasks to database or file."""
    if not USE_DATABASE:
        # File-based fallback
        TASKS_FILE.write_text(json.dumps(tasks, indent=2))

async def add_task_to_storage(title: str, priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
    """Add task to storage (database or file)."""
    if USE_DATABASE:
        task = await db_add_task(title, priority, due_date)
        return format_task_for_json(dict(task))
    else:
        # File-based fallback
        tasks = await load_tasks()
        
        # Find the highest existing ID and increment it
        if tasks:
            max_id = max(task["id"] for task in tasks)
            new_id = max_id + 1
        else:
            new_id = 1
        
        task = {
            "id": new_id,
            "title": title,
            "priority": priority,
            "due_date": due_date,
            "created": datetime.now().isoformat(),
            "completed": False,
            "completed_at": None
        }
        tasks.append(task)
        await save_tasks(tasks)
        return task

async def update_task_completion(task_id: int, completed: bool) -> bool:
    """Update task completion status."""
    if USE_DATABASE:
        return await db_update_task_completed(task_id, completed)
    else:
        # File-based fallback
        tasks = await load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                task["completed"] = completed
                task["completed_at"] = datetime.now().isoformat() if completed else None
                await save_tasks(tasks)
                return True
        return False

async def delete_task_from_storage(task_id: int) -> bool:
    """Delete task from storage."""
    if USE_DATABASE:
        return await db_delete_task(task_id)
    else:
        # File-based fallback
        tasks = await load_tasks()
        original_count = len(tasks)
        tasks = [task for task in tasks if task["id"] != task_id]
        
        if len(tasks) < original_count:
            await save_tasks(tasks)
            return True
        return False

async def update_task_priority_in_storage(task_id: int, priority: str) -> bool:
    """Update task priority in storage."""
    if USE_DATABASE:
        return await db_update_task_priority(task_id, priority)
    else:
        # File-based fallback
        tasks = await load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                task["priority"] = priority
                await save_tasks(tasks)
                return True
        return False

async def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    """Get task by ID from storage."""
    if USE_DATABASE:
        task = await db_get_task_by_id(task_id)
        return format_task_for_json(task) if task else None
    else:
        # File-based fallback
        tasks = await load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                return task
        return None

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
    
    storage_type = "PostgreSQL" if USE_DATABASE else "File"
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
        "storage_type": "PostgreSQL" if USE_DATABASE else "File"
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
    storage_type = "PostgreSQL" if USE_DATABASE else "File"
    
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
    storage_type = "PostgreSQL" if USE_DATABASE else "File"
    
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
        storage_type = "PostgreSQL" if USE_DATABASE else "File"
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
    
    storage_type = "PostgreSQL" if USE_DATABASE else "File"
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
    await init_database()

async def cleanup():
    """Clean up resources."""
    await close_database()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    is_deployment = os.getenv("PORT") is not None or os.getenv("RAILWAY_ENVIRONMENT") is not None
    is_stdio_mode = not sys.stdin.isatty() and not is_deployment
    
    if is_stdio_mode:
        # Run in stdio mode for local MCP clients
        asyncio.run(startup())
        try:
            mcp.run()
        finally:
            asyncio.run(cleanup())
    else:
        # HTTP server mode
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