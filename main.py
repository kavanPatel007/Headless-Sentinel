#!/usr/bin/env python3
"""
Headless Sentinel - Lightweight CLI-Driven Log Aggregator for Windows
Main Entry Point

Author: Senior Principal Security Engineer
License: MIT
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from collector import LogCollector
from analyzer import LogAnalyzer, Watcher, Responder
from config_manager import ConfigManager
from utils import setup_logging, validate_environment

console = Console()
logger = setup_logging()


@click.group()
@click.version_option(version="1.0.0", prog_name="Headless Sentinel")
def cli():
    """
    Headless Sentinel - Production-Grade Log Aggregation & Analysis
    
    A lightweight, CLI-driven alternative to Splunk for Windows environments.
    """
    pass


@cli.command()
@click.option(
    '--config',
    '-c',
    type=click.Path(exists=True),
    default='config.yaml',
    help='Path to configuration file'
)
@click.option(
    '--continuous',
    is_flag=True,
    help='Run in continuous mode (daemon-like)'
)
@click.option(
    '--interval',
    '-i',
    type=int,
    default=300,
    help='Collection interval in seconds (default: 300)'
)
def collect(config: str, continuous: bool, interval: int):
    """
    Collect logs from remote Windows machines.
    
    Examples:
        sentinel collect
        sentinel collect --continuous --interval 60
        sentinel collect -c custom_config.yaml
    """
    try:
        console.print(
            Panel.fit(
                "[bold cyan]Headless Sentinel - Log Collection[/bold cyan]",
                border_style="cyan"
            )
        )
        
        # Validate environment
        if not validate_environment():
            console.print("[red]✗[/red] Environment validation failed", style="bold")
            sys.exit(1)
        
        # Load configuration
        config_mgr = ConfigManager(config)
        
        # Initialize collector
        collector = LogCollector(config_mgr)
        
        if continuous:
            console.print(
                f"[green]✓[/green] Starting continuous collection "
                f"(interval: {interval}s)",
                style="bold"
            )
            asyncio.run(collector.run_continuous(interval))
        else:
            console.print("[green]✓[/green] Running one-time collection", style="bold")
            asyncio.run(collector.collect_all())
            console.print("[green]✓[/green] Collection completed", style="bold green")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]![/yellow] Collection interrupted by user", style="bold")
        sys.exit(0)
    except Exception as e:
        logger.exception("Collection failed")
        console.print(f"[red]✗[/red] Collection failed: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.option(
    '--query',
    '-q',
    type=str,
    help='SQL query to execute against log database'
)
@click.option(
    '--event-id',
    '-e',
    type=int,
    help='Filter by specific Event ID'
)
@click.option(
    '--severity',
    '-s',
    type=click.Choice(['critical', 'error', 'warning', 'information'], case_sensitive=False),
    help='Filter by severity level'
)
@click.option(
    '--host',
    '-h',
    type=str,
    help='Filter by source hostname/IP'
)
@click.option(
    '--last',
    '-l',
    type=str,
    default='24h',
    help='Time range (e.g., 1h, 24h, 7d)'
)
@click.option(
    '--limit',
    type=int,
    default=100,
    help='Maximum number of results (default: 100)'
)
@click.option(
    '--export',
    type=click.Path(),
    help='Export results to CSV file'
)
def query(
    query: Optional[str],
    event_id: Optional[int],
    severity: Optional[str],
    host: Optional[str],
    last: str,
    limit: int,
    export: Optional[str]
):
    """
    Query collected logs using SQL or filters.
    
    Examples:
        sentinel query -e 4625 -l 1h
        sentinel query -s error --host 192.168.1.100
        sentinel query -q "SELECT * FROM logs WHERE event_id IN (4624, 4625)"
        sentinel query -e 4625 --export failed_logins.csv
    """
    try:
        analyzer = LogAnalyzer()
        
        if query:
            results = analyzer.execute_query(query, limit)
        else:
            results = analyzer.search_logs(
                event_id=event_id,
                severity=severity,
                host=host,
                time_range=last,
                limit=limit
            )
        
        if results.empty:
            console.print("[yellow]No results found[/yellow]")
            return
        
        # Display results
        table = Table(title=f"Query Results ({len(results)} records)")
        for col in results.columns:
            table.add_column(col, overflow="fold")
        
        for _, row in results.iterrows():
            table.add_row(*[str(val) for val in row])
        
        console.print(table)
        
        # Export if requested
        if export:
            results.to_csv(export, index=False)
            console.print(f"[green]✓[/green] Results exported to {export}")
            
    except Exception as e:
        logger.exception("Query failed")
        console.print(f"[red]✗[/red] Query failed: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.option(
    '--config',
    '-c',
    type=click.Path(exists=True),
    default='config.yaml',
    help='Path to configuration file'
)
def watch(config: str):
    """
    Start the Watcher daemon for proactive alerting.
    
    Monitors logs in real-time and triggers alerts based on configured rules.
    """
    try:
        console.print(
            Panel.fit(
                "[bold yellow]Headless Sentinel - Watcher Mode[/bold yellow]",
                border_style="yellow"
            )
        )
        
        config_mgr = ConfigManager(config)
        analyzer = LogAnalyzer()
        watcher = Watcher(config_mgr, analyzer)
        
        console.print("[green]✓[/green] Watcher started. Press Ctrl+C to stop.", style="bold")
        asyncio.run(watcher.start())
        
    except KeyboardInterrupt:
        console.print("\n[yellow]![/yellow] Watcher stopped by user", style="bold")
        sys.exit(0)
    except Exception as e:
        logger.exception("Watcher failed")
        console.print(f"[red]✗[/red] Watcher failed: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.option(
    '--output',
    '-o',
    type=click.Path(),
    default='security_report.md',
    help='Output path for the report'
)
@click.option(
    '--period',
    '-p',
    type=str,
    default='24h',
    help='Reporting period (e.g., 24h, 7d)'
)
@click.option(
    '--format',
    '-f',
    type=click.Choice(['markdown', 'html', 'json']),
    default='markdown',
    help='Output format'
)
def report(output: str, period: str, format: str):
    """
    Generate security posture report.
    
    Creates a comprehensive report of security events and anomalies.
    
    Examples:
        sentinel report
        sentinel report -p 7d -o weekly_report.md
        sentinel report -f html -o report.html
    """
    try:
        console.print(
            Panel.fit(
                "[bold magenta]Generating Security Report[/bold magenta]",
                border_style="magenta"
            )
        )
        
        analyzer = LogAnalyzer()
        
        with console.status("[bold green]Analyzing logs..."):
            report_data = analyzer.generate_report(period)
        
        # Generate report in specified format
        if format == 'markdown':
            report_content = analyzer.format_markdown_report(report_data)
        elif format == 'html':
            report_content = analyzer.format_html_report(report_data)
        else:  # json
            report_content = analyzer.format_json_report(report_data)
        
        # Write report
        Path(output).write_text(report_content, encoding='utf-8')
        
        console.print(f"[green]✓[/green] Report generated: {output}", style="bold green")
        console.print(f"   Period: {period}")
        console.print(f"   Format: {format}")
        
    except Exception as e:
        logger.exception("Report generation failed")
        console.print(f"[red]✗[/red] Report generation failed: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.option(
    '--follow',
    '-f',
    is_flag=True,
    help='Follow log stream (like tail -f)'
)
@click.option(
    '--filter',
    type=str,
    help='Filter expression (e.g., "event_id=4625")'
)
@click.option(
    '--lines',
    '-n',
    type=int,
    default=50,
    help='Number of lines to show initially (default: 50)'
)
def tail(follow: bool, filter: Optional[str], lines: int):
    """
    Tail logs in real-time with color-coded severity.
    
    Examples:
        sentinel tail -f
        sentinel tail -n 100
        sentinel tail -f --filter "event_id=4625"
    """
    try:
        analyzer = LogAnalyzer()
        
        if follow:
            console.print(
                "[green]✓[/green] Streaming logs (Press Ctrl+C to stop)...",
                style="bold"
            )
            asyncio.run(analyzer.tail_logs(filter_expr=filter))
        else:
            results = analyzer.get_recent_logs(lines, filter_expr=filter)
            for _, log in results.iterrows():
                analyzer.print_log_entry(log)
                
    except KeyboardInterrupt:
        console.print("\n[yellow]![/yellow] Tail stopped by user", style="bold")
        sys.exit(0)
    except Exception as e:
        logger.exception("Tail failed")
        console.print(f"[red]✗[/red] Tail failed: {e}", style="bold red")
        sys.exit(1)


@cli.command()
def status():
    """
    Display system status and statistics.
    """
    try:
        analyzer = LogAnalyzer()
        stats = analyzer.get_statistics()
        
        # Create status panel
        table = Table(title="Headless Sentinel Status", show_header=True)
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="green")
        
        table.add_row("Total Logs", f"{stats['total_logs']:,}")
        table.add_row("Unique Hosts", f"{stats['unique_hosts']:,}")
        table.add_row("Critical Events", f"{stats['critical_count']:,}")
        table.add_row("Error Events", f"{stats['error_count']:,}")
        table.add_row("Warning Events", f"{stats['warning_count']:,}")
        table.add_row("Database Size", stats['db_size'])
        table.add_row("Oldest Log", stats['oldest_log'])
        table.add_row("Newest Log", stats['newest_log'])
        
        console.print(table)
        
        # Top event IDs
        if stats['top_event_ids']:
            console.print("\n[bold cyan]Top Event IDs:[/bold cyan]")
            for event_id, count in stats['top_event_ids']:
                console.print(f"  • Event {event_id}: {count:,} occurrences")
        
    except Exception as e:
        logger.exception("Status check failed")
        console.print(f"[red]✗[/red] Status check failed: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.confirmation_option(prompt='Are you sure you want to initialize the database?')
def init():
    """
    Initialize the DuckDB database and schema.
    """
    try:
        console.print("[yellow]Initializing database...[/yellow]")
        analyzer = LogAnalyzer()
        analyzer.initialize_database()
        console.print("[green]✓[/green] Database initialized successfully", style="bold green")
    except Exception as e:
        logger.exception("Initialization failed")
        console.print(f"[red]✗[/red] Initialization failed: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.argument('config_path', type=click.Path(), default='config.yaml')
def generate_config(config_path: str):
    """
    Generate a sample configuration file.
    """
    try:
        ConfigManager.generate_sample_config(config_path)
        console.print(
            f"[green]✓[/green] Sample configuration generated: {config_path}",
            style="bold green"
        )
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to generate config: {e}", style="bold red")
        sys.exit(1)


if __name__ == '__main__':
    cli()
