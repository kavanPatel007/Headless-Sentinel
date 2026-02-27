"""
Headless Sentinel - Database Manager Module

Handles DuckDB database operations and schema management.
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import threading

import duckdb
import pandas as pd

from utils import setup_logging

logger = setup_logging()


class DatabaseManager:
    """Thread-safe DuckDB database manager"""
    
    def __init__(self, db_path: str = 'sentinel.duckdb'):
        self.db_path = db_path
        self._local = threading.local()
        self.initialize_schema()
    
    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = duckdb.connect(self.db_path)
        return self._local.conn
    
    def initialize_schema(self):
        """Create database schema if it doesn't exist"""
        
        schema_sql = """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            computer VARCHAR NOT NULL,
            log_name VARCHAR NOT NULL,
            event_id INTEGER NOT NULL,
            level VARCHAR NOT NULL,
            source VARCHAR,
            message TEXT,
            user VARCHAR,
            raw_xml TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE SEQUENCE IF NOT EXISTS logs_id_seq START 1;
        
        CREATE INDEX IF NOT EXISTS idx_timestamp ON logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_event_id ON logs(event_id);
        CREATE INDEX IF NOT EXISTS idx_computer ON logs(computer);
        CREATE INDEX IF NOT EXISTS idx_level ON logs(level);
        CREATE INDEX IF NOT EXISTS idx_composite ON logs(timestamp, event_id, computer);
        """
        
        try:
            self.connection.execute(schema_sql)
            self.connection.commit()
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise
    
    def insert_logs(self, log_entries: List[Any]):
        """Bulk insert log entries"""
        
        if not log_entries:
            return
        
        # Convert to DataFrame for efficient insertion
        data = []
        for entry in log_entries:
            data.append({
                'timestamp': entry.timestamp,
                'computer': entry.computer,
                'log_name': entry.log_name,
                'event_id': entry.event_id,
                'level': entry.level,
                'source': entry.source,
                'message': entry.message,
                'user': entry.user,
                'raw_xml': entry.raw_xml
            })
        
        df = pd.DataFrame(data)
        
        try:
            # Use DuckDB's efficient INSERT FROM SELECT
            self.connection.register('temp_logs', df)
            
            insert_sql = """
            INSERT INTO logs (id, timestamp, computer, log_name, event_id, level, source, message, user, raw_xml)
            SELECT 
                nextval('logs_id_seq'),
                timestamp,
                computer,
                log_name,
                event_id,
                level,
                source,
                message,
                user,
                raw_xml
            FROM temp_logs
            """
            
            self.connection.execute(insert_sql)
            self.connection.commit()
            self.connection.unregister('temp_logs')
            
            logger.info(f"Inserted {len(log_entries)} log entries")
            
        except Exception as e:
            logger.error(f"Failed to insert logs: {e}")
            raise
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute SQL query and return DataFrame"""
        
        try:
            result = self.connection.execute(query).fetchdf()
            return result
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def get_table_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        
        stats = {}
        
        try:
            # Row count
            result = self.connection.execute("SELECT COUNT(*) as count FROM logs").fetchone()
            stats['total_rows'] = result[0]
            
            # Database size
            db_file = Path(self.db_path)
            if db_file.exists():
                stats['size_bytes'] = db_file.stat().st_size
                stats['size_mb'] = stats['size_bytes'] / (1024 * 1024)
            
            # Date range
            result = self.connection.execute(
                "SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts FROM logs"
            ).fetchone()
            stats['earliest_log'] = result[0]
            stats['latest_log'] = result[1]
            
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
        
        return stats
    
    def vacuum(self):
        """Optimize database"""
        try:
            self.connection.execute("VACUUM")
            self.connection.execute("ANALYZE")
            logger.info("Database vacuumed and analyzed")
        except Exception as e:
            logger.error(f"Vacuum failed: {e}")
    
    def export_to_parquet(self, output_path: str, filters: Optional[str] = None):
        """Export logs to Parquet format"""
        
        query = "SELECT * FROM logs"
        if filters:
            query += f" WHERE {filters}"
        
        try:
            self.connection.execute(
                f"COPY ({query}) TO '{output_path}' (FORMAT PARQUET)"
            )
            logger.info(f"Exported to {output_path}")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise
    
    def import_from_parquet(self, input_path: str):
        """Import logs from Parquet format"""
        
        try:
            self.connection.execute(
                f"INSERT INTO logs SELECT * FROM read_parquet('{input_path}')"
            )
            self.connection.commit()
            logger.info(f"Imported from {input_path}")
        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise
    
    def delete_old_logs(self, days: int):
        """Delete logs older than specified days"""
        
        try:
            result = self.connection.execute(f"""
                DELETE FROM logs 
                WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
            """)
            deleted = result.fetchone()[0] if result else 0
            self.connection.commit()
            logger.info(f"Deleted {deleted} old log entries")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete old logs: {e}")
            raise
    
    def create_backup(self, backup_path: str):
        """Create database backup"""
        
        try:
            import shutil
            # Close connection to allow file copy
            self.close()
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Backup created: {backup_path}")
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
    
    def __del__(self):
        """Cleanup on deletion"""
        self.close()
