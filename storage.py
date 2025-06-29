"""
Storage abstraction layer using the Strategy pattern.
Provides clean separation between PostgreSQL and file-based storage.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import os
import asyncio
import asyncpg
from pathlib import Path


class StorageStrategy(ABC):
    """Abstract base class for storage strategies."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage backend."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources."""
        pass
    
    @abstractmethod
    async def add_task(self, title: str, priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
        """Add a new task and return the created task."""
        pass
    
    @abstractmethod
    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks."""
        pass
    
    @abstractmethod
    async def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific task by ID."""
        pass
    
    @abstractmethod
    async def update_task_completed(self, task_id: int, completed: bool) -> bool:
        """Update task completion status. Returns True if successful."""
        pass
    
    @abstractmethod
    async def delete_task(self, task_id: int) -> bool:
        """Delete a task. Returns True if successful."""
        pass
    
    @abstractmethod
    async def update_task_priority(self, task_id: int, priority: str) -> bool:
        """Update task priority. Returns True if successful."""
        pass
    
    @abstractmethod
    def get_storage_type(self) -> str:
        """Return a string identifying the storage type."""
        pass


class PostgreSQLStorage(StorageStrategy):
    """PostgreSQL storage implementation."""
    
    def __init__(self, database_url: str, table_name: str = "tasks"):
        self.database_url = database_url
        self.table_name = table_name
        self.db_pool = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize database connection and create tables if needed."""
        if self._initialized:
            return
        
        try:
            print("🐘 Connecting to PostgreSQL...")
            # Create connection pool with Railway-friendly settings
            self.db_pool = await asyncpg.create_pool(
                self.database_url, 
                min_size=1, 
                max_size=10,
                command_timeout=30,
                server_settings={
                    'application_name': 'fastmcp_todo'
                }
            )
            
            # Test the connection and create tasks table if it doesn't exist
            async with self.db_pool.acquire() as conn:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
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
            self._initialized = True
            
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            # Clean up any partial pool
            if self.db_pool:
                try:
                    await self.db_pool.close()
                except:
                    pass
                self.db_pool = None
            raise
    
    async def close(self) -> None:
        """Close database connections."""
        if self.db_pool:
            try:
                await self.db_pool.close()
            except Exception as e:
                print(f"Warning: Error closing database pool: {e}")
            finally:
                self.db_pool = None
        self._initialized = False
    
    async def add_task(self, title: str, priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
        """Add task to database."""
        await self.initialize()
        assert self.db_pool is not None
        
        async with self.db_pool.acquire() as conn:
            task_id = await conn.fetchval(f"""
                INSERT INTO {self.table_name} (title, priority, due_date)
                VALUES ($1, $2, $3)
                RETURNING id
            """, title, priority, due_date)
            
            # Return the full task
            row = await conn.fetchrow(f"""
                SELECT id, title, priority, due_date, created, completed, completed_at
                FROM {self.table_name} WHERE id = $1
            """, task_id)
            return self._format_task_for_json(dict(row))
    
    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks from database."""
        await self.initialize()
        assert self.db_pool is not None
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, title, priority, due_date, created, completed, completed_at
                FROM {self.table_name}
                ORDER BY id
            """)
            return [self._format_task_for_json(dict(row)) for row in rows]
    
    async def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get specific task by ID."""
        await self.initialize()
        assert self.db_pool is not None
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                SELECT id, title, priority, due_date, created, completed, completed_at
                FROM {self.table_name} WHERE id = $1
            """, task_id)
            return self._format_task_for_json(dict(row)) if row else None
    
    async def update_task_completed(self, task_id: int, completed: bool) -> bool:
        """Update task completion status."""
        await self.initialize()
        assert self.db_pool is not None
        
        async with self.db_pool.acquire() as conn:
            completed_at = datetime.now() if completed else None
            result = await conn.execute(f"""
                UPDATE {self.table_name} 
                SET completed = $1, completed_at = $2
                WHERE id = $3
            """, completed, completed_at, task_id)
            return result != "UPDATE 0"
    
    async def delete_task(self, task_id: int) -> bool:
        """Delete task from database."""
        await self.initialize()
        assert self.db_pool is not None
        
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(f"DELETE FROM {self.table_name} WHERE id = $1", task_id)
            return result != "DELETE 0"
    
    async def update_task_priority(self, task_id: int, priority: str) -> bool:
        """Update task priority."""
        await self.initialize()
        assert self.db_pool is not None
        
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(f"""
                UPDATE {self.table_name} SET priority = $1 WHERE id = $2
            """, priority, task_id)
            return result != "UPDATE 0"
    
    def get_storage_type(self) -> str:
        """Return storage type identifier."""
        return "PostgreSQL"
    
    def _format_task_for_json(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database task to JSON-compatible format."""
        formatted_task = task.copy()
        if task.get('created') and hasattr(task['created'], 'isoformat'):
            formatted_task['created'] = task['created'].isoformat()
        if task.get('completed_at') and hasattr(task['completed_at'], 'isoformat'):
            formatted_task['completed_at'] = task['completed_at'].isoformat()
        return formatted_task


class FileStorage(StorageStrategy):
    """File-based storage implementation."""
    
    def __init__(self, file_path: str = "tasks.json"):
        self.file_path = Path(file_path)
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize file storage."""
        print("📁 Using file-based storage")
        # Create empty file if it doesn't exist
        if not self.file_path.exists():
            await self._save_tasks([])
    
    async def close(self) -> None:
        """No cleanup needed for file storage."""
        pass
    
    async def add_task(self, title: str, priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
        """Add task to file."""
        async with self._lock:
            tasks = await self._load_tasks()
            
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
            await self._save_tasks(tasks)
            return task
    
    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks from file."""
        return await self._load_tasks()
    
    async def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get specific task by ID."""
        tasks = await self._load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                return task
        return None
    
    async def update_task_completed(self, task_id: int, completed: bool) -> bool:
        """Update task completion status."""
        async with self._lock:
            tasks = await self._load_tasks()
            for task in tasks:
                if task["id"] == task_id:
                    task["completed"] = completed
                    task["completed_at"] = datetime.now().isoformat() if completed else None
                    await self._save_tasks(tasks)
                    return True
            return False
    
    async def delete_task(self, task_id: int) -> bool:
        """Delete task from file."""
        async with self._lock:
            tasks = await self._load_tasks()
            original_count = len(tasks)
            tasks = [task for task in tasks if task["id"] != task_id]
            
            if len(tasks) < original_count:
                await self._save_tasks(tasks)
                return True
            return False
    
    async def update_task_priority(self, task_id: int, priority: str) -> bool:
        """Update task priority."""
        async with self._lock:
            tasks = await self._load_tasks()
            for task in tasks:
                if task["id"] == task_id:
                    task["priority"] = priority
                    await self._save_tasks(tasks)
                    return True
            return False
    
    def get_storage_type(self) -> str:
        """Return storage type identifier."""
        return "File"
    
    async def _load_tasks(self) -> List[Dict[str, Any]]:
        """Load tasks from file."""
        if self.file_path.exists():
            try:
                return json.loads(self.file_path.read_text())
            except json.JSONDecodeError:
                return []
        return []
    
    async def _save_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        """Save tasks to file."""
        self.file_path.write_text(json.dumps(tasks, indent=2))


class StorageFactory:
    """Factory to create appropriate storage strategy."""
    
    @staticmethod
    def create_storage(database_url: Optional[str] = None, 
                      file_path: str = "tasks.json",
                      table_name: str = "tasks") -> StorageStrategy:
        """Create appropriate storage strategy based on configuration."""
        if database_url:
            return PostgreSQLStorage(database_url, table_name)
        else:
            return FileStorage(file_path)