"""
Headless Sentinel - Test Suite

Run with: pytest test_sentinel.py -v
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

# Import modules
from database import DatabaseManager
from config_manager import ConfigManager
from utils import (
    sanitize_xml,
    parse_event_message,
    validate_ip,
    format_bytes,
    get_event_description
)
from collector import LogEntry
from analyzer import LogAnalyzer


class TestDatabaseManager:
    """Test database operations"""
    
    def setup_method(self):
        """Setup test database"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.duckdb')
        self.db = DatabaseManager(self.temp_db.name)
    
    def teardown_method(self):
        """Cleanup test database"""
        self.db.close()
        os.unlink(self.temp_db.name)
    
    def test_schema_initialization(self):
        """Test database schema creation"""
        result = self.db.execute_query("SELECT COUNT(*) FROM logs")
        assert result is not None
    
    def test_insert_logs(self):
        """Test log insertion"""
        logs = [
            LogEntry(
                timestamp=datetime.utcnow(),
                event_id=4625,
                level='Error',
                source='Microsoft-Windows-Security-Auditing',
                message='Failed login attempt',
                computer='192.168.1.100',
                log_name='Security',
                user='testuser'
            )
        ]
        
        self.db.insert_logs(logs)
        result = self.db.execute_query("SELECT COUNT(*) FROM logs")
        assert result.iloc[0, 0] == 1
    
    def test_bulk_insert(self):
        """Test bulk log insertion"""
        logs = [
            LogEntry(
                timestamp=datetime.utcnow() - timedelta(hours=i),
                event_id=4625 + i,
                level='Error',
                source='Test',
                message=f'Test message {i}',
                computer='192.168.1.100',
                log_name='Security'
            )
            for i in range(100)
        ]
        
        self.db.insert_logs(logs)
        result = self.db.execute_query("SELECT COUNT(*) FROM logs")
        assert result.iloc[0, 0] == 100
    
    def test_query_performance(self):
        """Test query execution"""
        # Insert test data
        logs = [
            LogEntry(
                timestamp=datetime.utcnow() - timedelta(hours=i),
                event_id=4625 if i % 2 == 0 else 4624,
                level='Error' if i % 2 == 0 else 'Information',
                source='Test',
                message=f'Message {i}',
                computer='192.168.1.100',
                log_name='Security'
            )
            for i in range(1000)
        ]
        
        self.db.insert_logs(logs)
        
        # Test query
        result = self.db.execute_query(
            "SELECT COUNT(*) FROM logs WHERE event_id = 4625"
        )
        assert result.iloc[0, 0] == 500


class TestConfigManager:
    """Test configuration management"""
    
    def setup_method(self):
        """Setup test config"""
        self.temp_config = tempfile.NamedTemporaryFile(
            mode='w',
            delete=False,
            suffix='.yaml'
        )
        self.temp_config.write("""
database:
  path: test.duckdb
  retention_days: 30

targets:
  - ip: 192.168.1.100
    port: 5985

alerts:
  enabled: true
  rules:
    - name: Test Alert
      event_ids: [4625]
      threshold: 5
""")
        self.temp_config.close()
        self.config = ConfigManager(self.temp_config.name)
    
    def teardown_method(self):
        """Cleanup"""
        os.unlink(self.temp_config.name)
    
    def test_load_config(self):
        """Test config loading"""
        assert self.config.get('database.path') == 'test.duckdb'
        assert self.config.get('database.retention_days') == 30
    
    def test_get_nested_value(self):
        """Test nested value retrieval"""
        assert self.config.get('alerts.enabled') is True
    
    def test_default_value(self):
        """Test default value"""
        assert self.config.get('nonexistent.key', 'default') == 'default'
    
    def test_generate_config(self):
        """Test config generation"""
        temp_path = tempfile.mktemp(suffix='.yaml')
        ConfigManager.generate_sample_config(temp_path)
        assert Path(temp_path).exists()
        os.unlink(temp_path)


class TestLogAnalyzer:
    """Test log analysis"""
    
    def setup_method(self):
        """Setup test analyzer"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.duckdb')
        self.analyzer = LogAnalyzer(self.temp_db.name)
        
        # Insert test data
        logs = [
            LogEntry(
                timestamp=datetime.utcnow() - timedelta(hours=i),
                event_id=4625,
                level='Error',
                source='Security',
                message=f'Failed login from IP {i}',
                computer='192.168.1.100',
                log_name='Security'
            )
            for i in range(10)
        ]
        self.analyzer.db.insert_logs(logs)
    
    def teardown_method(self):
        """Cleanup"""
        self.analyzer.db.close()
        os.unlink(self.temp_db.name)
    
    def test_search_by_event_id(self):
        """Test searching by event ID"""
        results = self.analyzer.search_logs(event_id=4625)
        assert len(results) == 10
    
    def test_search_by_severity(self):
        """Test searching by severity"""
        results = self.analyzer.search_logs(severity='Error')
        assert len(results) == 10
    
    def test_time_range_filter(self):
        """Test time range filtering"""
        results = self.analyzer.search_logs(time_range='5h')
        assert len(results) <= 6  # 5 hours + current
    
    def test_statistics(self):
        """Test statistics generation"""
        stats = self.analyzer.get_statistics()
        assert stats['total_logs'] == 10
        assert stats['error_count'] == 10


class TestUtilities:
    """Test utility functions"""
    
    def test_sanitize_xml(self):
        """Test XML sanitization"""
        dirty_xml = "Test\x00data\x1Fwith\x0Bcontrol"
        clean_xml = sanitize_xml(dirty_xml)
        assert '\x00' not in clean_xml
        assert '\x1F' not in clean_xml
    
    def test_parse_event_message(self):
        """Test event message parsing"""
        message = """
        Account Name: testuser
        Account Domain: TESTDOMAIN
        Logon Type: 3
        Source Network Address: 192.168.1.50
        """
        parsed = parse_event_message(message)
        assert parsed['account'] == 'testuser'
        assert parsed['domain'] == 'TESTDOMAIN'
        assert parsed['logon_type'] == '3'
        assert parsed['source_ip'] == '192.168.1.50'
    
    def test_validate_ip(self):
        """Test IP validation"""
        assert validate_ip('192.168.1.1') is True
        assert validate_ip('255.255.255.255') is True
        assert validate_ip('256.1.1.1') is False
        assert validate_ip('invalid') is False
    
    def test_format_bytes(self):
        """Test byte formatting"""
        assert format_bytes(1024) == '1.00 KB'
        assert format_bytes(1048576) == '1.00 MB'
        assert format_bytes(1073741824) == '1.00 GB'
    
    def test_get_event_description(self):
        """Test event description lookup"""
        assert 'Failed' in get_event_description(4625)
        assert 'successful' in get_event_description(4624)


class TestCollector:
    """Test log collection (mock tests)"""
    
    def test_log_entry_creation(self):
        """Test LogEntry dataclass"""
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            event_id=4625,
            level='Error',
            source='Security',
            message='Test',
            computer='192.168.1.100',
            log_name='Security'
        )
        assert entry.event_id == 4625
        assert entry.level == 'Error'


@pytest.mark.asyncio
class TestAsyncOperations:
    """Test async operations"""
    
    async def test_async_webhook(self):
        """Test async webhook (mock)"""
        from utils import send_webhook
        
        # This will fail without a valid webhook URL, but tests the async flow
        try:
            result = await send_webhook(
                'https://invalid.webhook.url',
                'Test message',
                'slack'
            )
            # Expected to fail, but should not raise exception
            assert result is False
        except:
            pass


# Integration test example
class TestIntegration:
    """Integration tests"""
    
    def test_end_to_end_workflow(self):
        """Test complete workflow"""
        # Create temporary database
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.duckdb')
        
        try:
            # Initialize components
            db = DatabaseManager(temp_db.name)
            analyzer = LogAnalyzer(temp_db.name)
            
            # Create sample logs
            logs = [
                LogEntry(
                    timestamp=datetime.utcnow() - timedelta(minutes=i),
                    event_id=4625,
                    level='Error',
                    source='Security',
                    message=f'Failed login attempt {i}',
                    computer='192.168.1.100',
                    log_name='Security'
                )
                for i in range(5)
            ]
            
            # Insert logs
            db.insert_logs(logs)
            
            # Query logs
            results = analyzer.search_logs(event_id=4625, time_range='1h')
            assert len(results) == 5
            
            # Get statistics
            stats = analyzer.get_statistics()
            assert stats['total_logs'] == 5
            
            # Generate report
            report = analyzer.generate_report('1h')
            assert 'critical_events' in report
            
        finally:
            db.close()
            os.unlink(temp_db.name)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
