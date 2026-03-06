"""
Headless Sentinel - Log Analyzer Module

Implements DuckDB-based analytical engine, alerting, and reporting.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.live import Live
from rich.table import Table

from config_manager import ConfigManager
from database import DatabaseManager
from utils import setup_logging, send_webhook, execute_powershell_remote

console = Console()
logger = setup_logging()


class LogAnalyzer:
    """DuckDB-based log analyzer with SQL query capabilities"""
    
    SEVERITY_COLORS = {
        'Critical': 'bold red',
        'Error': 'red',
        'Warning': 'yellow',
        'Information': 'blue',
        'Verbose': 'dim'
    }
    
    def __init__(self, db_path: str = 'sentinel.duckdb'):
        self.db = DatabaseManager(db_path)
    
    def initialize_database(self):
        """Initialize database schema"""
        self.db.initialize_schema()
    
    def execute_query(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Execute raw SQL query"""
        if limit:
            query = f"{query.rstrip(';')} LIMIT {limit}"
        return self.db.execute_query(query)
    
    def search_logs(
        self,
        event_id: Optional[int] = None,
        severity: Optional[str] = None,
        host: Optional[str] = None,
        time_range: str = '24h',
        limit: int = 100
    ) -> pd.DataFrame:
        """Search logs with filters"""
        
        # Parse time range
        hours = self._parse_time_range(time_range)
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Build WHERE clause
        conditions = [f"timestamp >= '{start_time.isoformat()}'"]
        
        if event_id:
            conditions.append(f"event_id = {event_id}")
        if severity:
            conditions.append(f"LOWER(level) = '{severity.lower()}'")
        if host:
            conditions.append(f"computer LIKE '%{host}%'")
        
        where_clause = ' AND '.join(conditions)
        
        query = f"""
        SELECT 
            timestamp,
            computer,
            log_name,
            event_id,
            level,
            source,
            message
        FROM logs
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        
        return self.db.execute_query(query)
    
    def get_recent_logs(
        self,
        count: int = 50,
        filter_expr: Optional[str] = None
    ) -> pd.DataFrame:
        """Get most recent logs"""
        
        query = "SELECT * FROM logs"
        
        if filter_expr:
            # Simple filter parsing (e.g., "event_id=4625")
            query += f" WHERE {filter_expr}"
        
        query += f" ORDER BY timestamp DESC LIMIT {count}"
        
        return self.db.execute_query(query)
    
    async def tail_logs(
        self,
        interval: int = 2,
        filter_expr: Optional[str] = None
    ):
        """Tail logs in real-time"""
        
        last_timestamp = datetime.utcnow()
        
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                try:
                    # Query new logs
                    query = f"""
                    SELECT * FROM logs 
                    WHERE timestamp > '{last_timestamp.isoformat()}'
                    """
                    
                    if filter_expr:
                        query += f" AND {filter_expr}"
                    
                    query += " ORDER BY timestamp ASC LIMIT 100"
                    
                    new_logs = self.db.execute_query(query)
                    
                    if not new_logs.empty:
                        # Create table
                        table = Table(title="Log Stream")
                        table.add_column("Time", style="cyan")
                        table.add_column("Host", style="magenta")
                        table.add_column("Event", style="yellow")
                        table.add_column("Level", style="white")
                        table.add_column("Message", overflow="fold")
                        
                        for _, log in new_logs.iterrows():
                            time_str = log['timestamp'].strftime('%H:%M:%S')
                            level_style = self.SEVERITY_COLORS.get(
                                log['level'],
                                'white'
                            )
                            
                            table.add_row(
                                time_str,
                                log['computer'],
                                str(log['event_id']),
                                f"[{level_style}]{log['level']}[/{level_style}]",
                                log['message'][:100]
                            )
                        
                        live.update(table)
                        last_timestamp = new_logs['timestamp'].max()
                    
                    await asyncio.sleep(interval)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Error in tail: {e}")
                    await asyncio.sleep(interval)
    
    def print_log_entry(self, log: pd.Series):
        """Print a single log entry with color coding"""
        
        level = log['level']
        style = self.SEVERITY_COLORS.get(level, 'white')
        
        timestamp = log['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        
        console.print(
            f"[cyan]{timestamp}[/cyan] "
            f"[magenta]{log['computer']}[/magenta] "
            f"[yellow]Event {log['event_id']}[/yellow] "
            f"[{style}]{level}[/{style}] "
            f"{log['message'][:200]}"
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        
        stats = {}
        
        # Total logs
        result = self.db.execute_query("SELECT COUNT(*) as count FROM logs")
        stats['total_logs'] = result['count'].iloc[0]
        
        # Unique hosts
        result = self.db.execute_query(
            "SELECT COUNT(DISTINCT computer) as count FROM logs"
        )
        stats['unique_hosts'] = result['count'].iloc[0]
        
        # Severity breakdown
        result = self.db.execute_query("""
            SELECT level, COUNT(*) as count 
            FROM logs 
            GROUP BY level
        """)
        for _, row in result.iterrows():
            stats[f"{row['level'].lower()}_count"] = row['count']
        
        stats.setdefault('critical_count', 0)
        stats.setdefault('error_count', 0)
        stats.setdefault('warning_count', 0)
        
        # Time range
        result = self.db.execute_query(
            "SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest FROM logs"
        )
        if not result.empty:
            stats['oldest_log'] = str(result['oldest'].iloc[0])
            stats['newest_log'] = str(result['newest'].iloc[0])
        else:
            stats['oldest_log'] = 'N/A'
            stats['newest_log'] = 'N/A'
        
        # Database size
        db_path = Path(self.db.db_path)
        if db_path.exists():
            size_mb = db_path.stat().st_size / (1024 * 1024)
            stats['db_size'] = f"{size_mb:.2f} MB"
        else:
            stats['db_size'] = '0 MB'
        
        # Top event IDs
        result = self.db.execute_query("""
            SELECT event_id, COUNT(*) as count 
            FROM logs 
            GROUP BY event_id 
            ORDER BY count DESC 
            LIMIT 10
        """)
        stats['top_event_ids'] = list(result.itertuples(index=False, name=None))
        
        return stats
    
    def generate_report(self, period: str = '24h') -> Dict[str, Any]:
        """Generate security posture report data"""
        
        hours = self._parse_time_range(period)
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'period': period,
            'start_time': start_time.isoformat()
        }
        
        # Critical security events
        critical_events = self.db.execute_query(f"""
            SELECT event_id, COUNT(*) as count, computer
            FROM logs
            WHERE timestamp >= '{start_time.isoformat()}'
            AND event_id IN (4625, 4624, 4648, 4720, 4732, 4672)
            GROUP BY event_id, computer
            ORDER BY count DESC
        """)
        report['critical_events'] = critical_events.to_dict('records')
        
        # Failed login attempts (Event ID 4625)
        failed_logins = self.db.execute_query(f"""
            SELECT computer, COUNT(*) as count
            FROM logs
            WHERE timestamp >= '{start_time.isoformat()}'
            AND event_id = 4625
            GROUP BY computer
            ORDER BY count DESC
        """)
        report['failed_logins'] = failed_logins.to_dict('records')
        
        # Error summary
        errors = self.db.execute_query(f"""
            SELECT computer, log_name, COUNT(*) as count
            FROM logs
            WHERE timestamp >= '{start_time.isoformat()}'
            AND level IN ('Critical', 'Error')
            GROUP BY computer, log_name
            ORDER BY count DESC
            LIMIT 20
        """)
        report['errors'] = errors.to_dict('records')
        
        # Host summary
        host_summary = self.db.execute_query(f"""
            SELECT 
                computer,
                COUNT(*) as total_events,
                SUM(CASE WHEN level = 'Critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN level = 'Error' THEN 1 ELSE 0 END) as errors,
                SUM(CASE WHEN level = 'Warning' THEN 1 ELSE 0 END) as warnings
            FROM logs
            WHERE timestamp >= '{start_time.isoformat()}'
            GROUP BY computer
            ORDER BY critical DESC, errors DESC
        """)
        report['host_summary'] = host_summary.to_dict('records')
        
        return report
    
    def format_markdown_report(self, report_data: Dict[str, Any]) -> str:
        """Format report as Markdown"""
        
        md = f"""# Headless Sentinel Security Report

**Generated:** {report_data['generated_at']}  
**Period:** {report_data['period']}  
**Start Time:** {report_data['start_time']}

---

## Executive Summary

This report provides an overview of security events and system health across monitored Windows hosts.

## Critical Security Events

"""
        
        if report_data['critical_events']:
            md += "| Event ID | Computer | Count | Description |\n"
            md += "|----------|----------|-------|-------------|\n"
            
            event_descriptions = {
                4625: "Failed Login Attempt",
                4624: "Successful Login",
                4648: "Logon with Explicit Credentials",
                4720: "User Account Created",
                4732: "User Added to Security Group",
                4672: "Special Privileges Assigned"
            }
            
            for event in report_data['critical_events']:
                desc = event_descriptions.get(event['event_id'], 'Unknown')
                md += f"| {event['event_id']} | {event['computer']} | {event['count']} | {desc} |\n"
        else:
            md += "*No critical security events detected.*\n"
        
        md += "\n## Failed Login Attempts\n\n"
        
        if report_data['failed_logins']:
            md += "| Computer | Failed Attempts |\n"
            md += "|----------|----------------|\n"
            for login in report_data['failed_logins']:
                md += f"| {login['computer']} | {login['count']} |\n"
        else:
            md += "*No failed login attempts detected.*\n"
        
        md += "\n## Error Summary\n\n"
        
        if report_data['errors']:
            md += "| Computer | Log Name | Error Count |\n"
            md += "|----------|----------|-------------|\n"
            for error in report_data['errors'][:10]:
                md += f"| {error['computer']} | {error['log_name']} | {error['count']} |\n"
        else:
            md += "*No critical errors detected.*\n"
        
        md += "\n## Host Summary\n\n"
        
        if report_data['host_summary']:
            md += "| Computer | Total Events | Critical | Errors | Warnings |\n"
            md += "|----------|--------------|----------|--------|----------|\n"
            for host in report_data['host_summary']:
                md += (
                    f"| {host['computer']} | {host['total_events']} | "
                    f"{host['critical']} | {host['errors']} | {host['warnings']} |\n"
                )
        
        md += "\n---\n\n*Report generated by Headless Sentinel*\n"
        
        return md
    
    def format_html_report(self, report_data: Dict[str, Any]) -> str:
        """Format report as HTML"""
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Headless Sentinel Security Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .critical {{ color: red; font-weight: bold; }}
        .warning {{ color: orange; }}
    </style>
</head>
<body>
    <h1>Headless Sentinel Security Report</h1>
    <p><strong>Generated:</strong> {report_data['generated_at']}</p>
    <p><strong>Period:</strong> {report_data['period']}</p>
    
    <h2>Critical Security Events</h2>
    <table>
        <tr><th>Event ID</th><th>Computer</th><th>Count</th></tr>
"""
        
        for event in report_data['critical_events']:
            html += f"<tr><td>{event['event_id']}</td><td>{event['computer']}</td><td>{event['count']}</td></tr>\n"
        
        html += """
    </table>
    
    <h2>Failed Login Attempts</h2>
    <table>
        <tr><th>Computer</th><th>Count</th></tr>
"""
        
        for login in report_data['failed_logins']:
            html += f"<tr><td>{login['computer']}</td><td class='warning'>{login['count']}</td></tr>\n"
        
        html += """
    </table>
</body>
</html>
"""
        return html
    
    def format_json_report(self, report_data: Dict[str, Any]) -> str:
        """Format report as JSON"""
        return json.dumps(report_data, indent=2, default=str)
    
    def _parse_time_range(self, time_range: str) -> int:
        """Parse time range string to hours"""
        
        time_range = time_range.lower().strip()
        
        if time_range.endswith('h'):
            return int(time_range[:-1])
        elif time_range.endswith('d'):
            return int(time_range[:-1]) * 24
        elif time_range.endswith('w'):
            return int(time_range[:-1]) * 24 * 7
        else:
            return int(time_range)


class Watcher:
    """Proactive alerting system"""
    
    def __init__(self, config: ConfigManager, analyzer: LogAnalyzer):
        self.config = config
        self.analyzer = analyzer
        self.alert_rules = config.get('alerts', {}).get('rules', [])
        self.check_interval = config.get('alerts', {}).get('check_interval', 60)
        self.last_check = datetime.utcnow() - timedelta(hours=1)
    
    async def start(self):
        """Start the watcher daemon"""
        
        logger.info("Watcher started")
        
        while True:
            try:
                await self._check_alerts()
                await asyncio.sleep(self.check_interval)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Watcher error: {e}")
                await asyncio.sleep(60)
    
    async def _check_alerts(self):
        """Check for alert conditions"""
        
        now = datetime.utcnow()
        
        for rule in self.alert_rules:
            try:
                await self._evaluate_rule(rule, now)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.get('name')}: {e}")
        
        self.last_check = now
    
    async def _evaluate_rule(self, rule: Dict[str, Any], now: datetime):
        """Evaluate a single alert rule"""
        
        # Build query from rule
        event_ids = rule.get('event_ids', [])
        severity = rule.get('severity')
        threshold = rule.get('threshold', 1)
        
        conditions = [f"timestamp >= '{self.last_check.isoformat()}'"]
        
        if event_ids:
            ids_str = ','.join(str(eid) for eid in event_ids)
            conditions.append(f"event_id IN ({ids_str})")
        
        if severity:
            conditions.append(f"level = '{severity}'")
        
        where_clause = ' AND '.join(conditions)
        
        query = f"""
        SELECT computer, event_id, COUNT(*) as count
        FROM logs
        WHERE {where_clause}
        GROUP BY computer, event_id
        HAVING count >= {threshold}
        """
        
        results = self.analyzer.db.execute_query(query)
        
        if not results.empty:
            await self._trigger_alert(rule, results)
    
    async def _trigger_alert(self, rule: Dict[str, Any], results: pd.DataFrame):
        """Trigger alert actions"""
        
        alert_name = rule.get('name', 'Unnamed Alert')
        actions = rule.get('actions', [])
        
        logger.warning(f"Alert triggered: {alert_name}")
        console.print(f"[red]🚨 ALERT:[/red] {alert_name}", style="bold")
        
        # Format alert message
        message = f"**Alert: {alert_name}**\n\n"
        message += "Triggered conditions:\n"
        for _, row in results.iterrows():
            message += f"- {row['computer']}: Event {row['event_id']} ({row['count']} times)\n"
        
        # Execute actions
        for action in actions:
            action_type = action.get('type')
            
            if action_type == 'webhook':
                await self._send_webhook_alert(action, message)
            elif action_type == 'email':
                await self._send_email_alert(action, message)
            elif action_type == 'remediation':
                await self._execute_remediation(action, results)
    
    async def _send_webhook_alert(self, action: Dict[str, Any], message: str):
        """Send webhook alert"""
        
        url = action.get('url')
        if not url:
            return
        
        try:
            await send_webhook(url, message, action.get('type_hint', 'slack'))
            logger.info(f"Webhook sent to {url}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
    
    async def _send_email_alert(self, action: Dict[str, Any], message: str):
        """Send email alert (placeholder)"""
        logger.info(f"Email alert: {message[:100]}")
    
    async def _execute_remediation(
        self,
        action: Dict[str, Any],
        results: pd.DataFrame
    ):
        """Execute automated remediation"""
        
        script = action.get('script')
        if not script:
            return
        
        for _, row in results.iterrows():
            computer = row['computer']
            logger.warning(f"Executing remediation on {computer}")
            # This would need credentials - placeholder for now
            # await execute_powershell_remote(computer, script)


class Responder:
    """Automated response system"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
    
    async def execute_response(
        self,
        target: str,
        script: str,
        credentials: Dict[str, str]
    ):
        """Execute PowerShell script on target"""
        
        try:
            result = await execute_powershell_remote(
                target,
                script,
                credentials['username'],
                credentials['password']
            )
            logger.info(f"Response executed on {target}: {result}")
            return result
        except Exception as e:
            logger.error(f"Response execution failed on {target}: {e}")
            raise
