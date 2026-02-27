"""
Headless Sentinel - Log Collector Module

Handles asynchronous remote log collection from Windows machines using WinRM.
Implements forwarder logic for multiple concurrent streams.
"""

import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import winrm
from winrm.protocol import Protocol
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from config_manager import ConfigManager
from database import DatabaseManager
from utils import setup_logging, retry_on_failure, sanitize_xml

console = Console()
logger = setup_logging()


@dataclass
class LogEntry:
    """Structured log entry"""
    timestamp: datetime
    event_id: int
    level: str
    source: str
    message: str
    computer: str
    log_name: str
    user: Optional[str] = None
    raw_xml: Optional[str] = None


class RemoteHost:
    """Represents a remote Windows host for log collection"""
    
    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        port: int = 5985,
        transport: str = 'ntlm',
        timeout: int = 120
    ):
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.transport = transport
        self.timeout = timeout
        self._session: Optional[winrm.Session] = None
        self._protocol = None
    
    def connect(self) -> bool:
        """Establish WinRM connection with proper timeout"""
        try:
            from winrm.protocol import Protocol
            
            endpoint = f'http://{self.ip}:{self.port}/wsman'
            
            # Calculate timeouts - read must exceed operation
            operation_timeout = self.timeout
            read_timeout = self.timeout + 30  # Must be higher than operation_timeout
            
            # Create session with timeout
            self._session = winrm.Session(
                endpoint,
                auth=(self.username, self.password),
                transport=self.transport,
                server_cert_validation='ignore',
                operation_timeout_sec=operation_timeout,
                read_timeout_sec=read_timeout
            )
            
            # Also create protocol for better control
            self._protocol = Protocol(
                endpoint=endpoint,
                transport=self.transport,
                username=self.username,
                password=self.password,
                server_cert_validation='ignore',
                read_timeout_sec=read_timeout,
                operation_timeout_sec=operation_timeout
            )
            
            # Test connection
            result = self._session.run_cmd('echo test')
            return result.status_code == 0
        except Exception as e:
            logger.error(f"Failed to connect to {self.ip}: {e}")
            return False
    
    @retry_on_failure(max_attempts=3, delay=5)
    def execute_powershell(self, script: str) -> Optional[str]:
        """Execute PowerShell script on remote host with proper timeout"""
        if not self._session or not self._protocol:
            if not self.connect():
                return None
        
        try:
            # Use protocol for better timeout control
            shell_id = self._protocol.open_shell()
            command_id = self._protocol.run_command(shell_id, 'powershell', ['-Command', script])
            std_out, std_err, status_code = self._protocol.get_command_output(shell_id, command_id)
            self._protocol.cleanup_command(shell_id, command_id)
            self._protocol.close_shell(shell_id)
            
            if status_code == 0:
                return std_out.decode('utf-8', errors='ignore')
            else:
                error = std_err.decode('utf-8', errors='ignore')
                logger.error(f"PowerShell error on {self.ip}: {error}")
                return None
        except Exception as e:
            logger.error(f"Failed to execute PowerShell on {self.ip}: {e}")
            # Fallback to session method
            try:
                result = self._session.run_ps(script)
                if result.status_code == 0:
                    return result.std_out.decode('utf-8', errors='ignore')
            except:
                pass
            return None
    
    def close(self):
        """Close the session"""
        self._session = None


class LogCollector:
    """Main log collection orchestrator"""
    
    # Event log severity mapping
    SEVERITY_MAP = {
        '1': 'Critical',
        '2': 'Error',
        '3': 'Warning',
        '4': 'Information',
        '5': 'Verbose'
    }
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.db = DatabaseManager(config.get('database', {}).get('path', 'sentinel.duckdb'))
        self.hosts: List[RemoteHost] = []
        self._initialize_hosts()
    
    def _initialize_hosts(self):
        """Initialize remote host connections"""
        targets = self.config.get('targets', [])
        
        for target in targets:
            try:
                # Get credentials
                creds = self.config.get_credentials(target['ip'])
                
                host = RemoteHost(
                    ip=target['ip'],
                    username=creds['username'],
                    password=creds['password'],
                    port=target.get('port', 5985),
                    transport=target.get('transport', 'ntlm'),
                    timeout=target.get('timeout', 30)
                )
                self.hosts.append(host)
                logger.info(f"Initialized host: {target['ip']}")
            except Exception as e:
                logger.error(f"Failed to initialize host {target.get('ip', 'unknown')}: {e}")
    
    async def collect_from_host(
        self,
        host: RemoteHost,
        log_names: List[str],
        hours_back: int = 1
    ) -> List[LogEntry]:
        """Collect logs from a single host asynchronously"""
        
        loop = asyncio.get_event_loop()
        all_entries = []
        
        for log_name in log_names:
            try:
                # Build PowerShell query
                script = self._build_event_query(log_name, hours_back)
                
                # Run in thread pool to avoid blocking
                xml_output = await loop.run_in_executor(
                    None,
                    host.execute_powershell,
                    script
                )
                
                if not xml_output:
                    continue
                
                # Parse XML output
                entries = self._parse_event_xml(xml_output, host.ip, log_name)
                all_entries.extend(entries)
                
                logger.info(
                    f"Collected {len(entries)} entries from {host.ip}/{log_name}"
                )
                
            except Exception as e:
                logger.error(
                    f"Failed to collect {log_name} from {host.ip}: {e}"
                )
        
        return all_entries
    
    def _build_event_query(self, log_name: str, hours_back: int) -> str:
        """Build PowerShell Get-WinEvent query"""
        
        # Calculate time filter
        start_time = datetime.utcnow() - timedelta(hours=hours_back)
        time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        # Build XPath filter for recent events
        script = f"""
$startTime = [DateTime]::Parse('{time_str}')
$events = Get-WinEvent -FilterHashtable @{{
    LogName='{log_name}'
    StartTime=$startTime
}} -ErrorAction SilentlyContinue -MaxEvents 10000

if ($events) {{
    $events | ForEach-Object {{
        $_.ToXml()
        Write-Output "---EVENT_SEPARATOR---"
    }}
}}
"""
        return script
    
    def _parse_event_xml(
        self,
        xml_output: str,
        computer: str,
        log_name: str
    ) -> List[LogEntry]:
        """Parse XML event log output"""
        
        entries = []
        events = xml_output.split('---EVENT_SEPARATOR---')
        
        for event_str in events:
            event_str = event_str.strip()
            if not event_str or len(event_str) < 50:
                continue
            
            try:
                # Sanitize XML
                event_str = sanitize_xml(event_str)
                root = ET.fromstring(event_str)
                
                # Extract System data
                system = root.find('.//{http://schemas.microsoft.com/win/2004/08/events/event}System')
                if system is None:
                    continue
                
                event_id_elem = system.find('.//{http://schemas.microsoft.com/win/2004/08/events/event}EventID')
                level_elem = system.find('.//{http://schemas.microsoft.com/win/2004/08/events/event}Level')
                time_elem = system.find('.//{http://schemas.microsoft.com/win/2004/08/events/event}TimeCreated')
                provider_elem = system.find('.//{http://schemas.microsoft.com/win/2004/08/events/event}Provider')
                
                if not all([event_id_elem, level_elem, time_elem]):
                    continue
                
                # Extract message
                event_data = root.find('.//{http://schemas.microsoft.com/win/2004/08/events/event}EventData')
                message_parts = []
                if event_data is not None:
                    for data in event_data.findall('.//{http://schemas.microsoft.com/win/2004/08/events/event}Data'):
                        if data.text:
                            message_parts.append(data.text)
                
                message = ' | '.join(message_parts) if message_parts else 'No message'
                
                # Create entry
                entry = LogEntry(
                    timestamp=datetime.fromisoformat(
                        time_elem.get('SystemTime').replace('Z', '+00:00')
                    ),
                    event_id=int(event_id_elem.text),
                    level=self.SEVERITY_MAP.get(level_elem.text, 'Unknown'),
                    source=provider_elem.get('Name') if provider_elem is not None else 'Unknown',
                    message=message[:1000],  # Limit message length
                    computer=computer,
                    log_name=log_name,
                    raw_xml=event_str[:5000]  # Store truncated XML
                )
                
                entries.append(entry)
                
            except ET.ParseError as e:
                logger.debug(f"XML parse error: {e}")
                continue
            except Exception as e:
                logger.error(f"Error parsing event: {e}")
                continue
        
        return entries
    
    async def collect_all(self):
        """Collect logs from all configured hosts"""
        
        log_names = self.config.get('collection', {}).get(
            'log_types',
            ['System', 'Security', 'Application']
        )
        hours_back = self.config.get('collection', {}).get('hours_back', 1)
        
        console.print(f"[cyan]Collecting from {len(self.hosts)} hosts...[/cyan]")
        
        # Create progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            
            task = progress.add_task(
                "[cyan]Collecting logs...",
                total=len(self.hosts)
            )
            
            # Collect from all hosts concurrently
            tasks = []
            for host in self.hosts:
                tasks.append(self.collect_from_host(host, log_names, hours_back))
            
            all_results = []
            for coro in asyncio.as_completed(tasks):
                try:
                    entries = await coro
                    all_results.extend(entries)
                    progress.update(task, advance=1)
                except Exception as e:
                    logger.error(f"Collection task failed: {e}")
                    progress.update(task, advance=1)
        
        # Store in database
        if all_results:
            console.print(f"[green]Storing {len(all_results)} log entries...[/green]")
            self.db.insert_logs(all_results)
            console.print(f"[green]✓ Stored {len(all_results)} entries[/green]")
        else:
            console.print("[yellow]No logs collected[/yellow]")
    
    async def run_continuous(self, interval: int = 300):
        """Run collector in continuous mode"""
        
        console.print(f"[cyan]Starting continuous collection (interval: {interval}s)[/cyan]")
        
        iteration = 1
        while True:
            try:
                console.print(f"\n[bold cyan]Collection Iteration #{iteration}[/bold cyan]")
                console.print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                await self.collect_all()
                
                console.print(
                    f"[green]✓ Iteration complete. "
                    f"Next collection in {interval} seconds[/green]"
                )
                
                iteration += 1
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Error in continuous collection: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    def cleanup(self):
        """Cleanup resources"""
        for host in self.hosts:
            host.close()
        self.db.close()


class ForwarderPool:
    """Manages a pool of forwarders for high-throughput collection"""
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
    
    async def forward_logs(
        self,
        collector: LogCollector,
        host: RemoteHost,
        log_names: List[str]
    ) -> List[LogEntry]:
        """Forward logs with concurrency control"""
        
        async with self.semaphore:
            return await collector.collect_from_host(host, log_names)
