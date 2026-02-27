"""
Headless Sentinel - Utilities Module

Common utility functions and helpers.
"""

import os
import sys
import logging
import asyncio
import re
from typing import Optional, Callable, Any
from functools import wraps
from pathlib import Path

import aiohttp
from rich.logging import RichHandler


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Setup logging with Rich handler"""
    
    # Create logs directory if it doesn't exist
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    logger = logging.getLogger("sentinel")
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        )
        logger.addHandler(file_handler)
    
    return logger


def validate_environment() -> bool:
    """Validate that the environment is properly configured"""
    
    logger = logging.getLogger("sentinel")
    
    # Check Python version
    if sys.version_info < (3, 8):
        logger.error("Python 3.8+ is required")
        return False
    
    # Check required packages
    required_packages = [
        'winrm',
        'duckdb',
        'pandas',
        'yaml',
        'keyring',
        'click',
        'rich',
        'aiohttp'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"Missing required packages: {', '.join(missing_packages)}")
        logger.info("Install with: pip install -r requirements.txt")
        return False
    
    return True


def retry_on_failure(
    max_attempts: int = 3,
    delay: int = 5,
    exceptions: tuple = (Exception,)
):
    """Decorator for retrying functions on failure"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger("sentinel")
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}"
                    )
                    logger.info(f"Retrying in {delay} seconds...")
                    
                    import time
                    time.sleep(delay)
            
            return None
        
        return wrapper
    return decorator


async def send_webhook(
    url: str,
    message: str,
    webhook_type: str = 'slack'
) -> bool:
    """Send webhook notification (Discord/Slack)"""
    
    logger = logging.getLogger("sentinel")
    
    # Format payload based on webhook type
    if webhook_type.lower() == 'discord':
        payload = {
            'content': message,
            'username': 'Headless Sentinel'
        }
    elif webhook_type.lower() == 'slack':
        payload = {
            'text': message,
            'username': 'Headless Sentinel',
            'icon_emoji': ':shield:'
        }
    else:
        # Generic JSON payload
        payload = {
            'message': message,
            'source': 'Headless Sentinel'
        }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200 or response.status == 204:
                    logger.info(f"Webhook sent successfully to {webhook_type}")
                    return True
                else:
                    logger.error(
                        f"Webhook failed with status {response.status}"
                    )
                    return False
    except Exception as e:
        logger.error(f"Failed to send webhook: {e}")
        return False


async def execute_powershell_remote(
    target: str,
    script: str,
    username: str,
    password: str,
    port: int = 5985
) -> Optional[str]:
    """Execute PowerShell script on remote host"""
    
    logger = logging.getLogger("sentinel")
    
    try:
        import winrm
        
        endpoint = f'http://{target}:{port}/wsman'
        session = winrm.Session(
            endpoint,
            auth=(username, password),
            transport='ntlm',
            server_cert_validation='ignore'
        )
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            session.run_ps,
            script
        )
        
        if result.status_code == 0:
            return result.std_out.decode('utf-8', errors='ignore')
        else:
            error = result.std_err.decode('utf-8', errors='ignore')
            logger.error(f"PowerShell execution failed: {error}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to execute PowerShell on {target}: {e}")
        return None


def sanitize_xml(xml_string: str) -> str:
    """Sanitize XML string by removing invalid characters"""
    
    # Remove null bytes and other control characters except tab, newline, carriage return
    xml_string = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', xml_string)
    
    # Remove invalid XML characters
    xml_string = re.sub(r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]', '', xml_string)
    
    return xml_string


def format_bytes(bytes_value: int) -> str:
    """Format bytes to human-readable string"""
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    
    return f"{bytes_value:.2f} PB"


def parse_event_message(message: str) -> dict:
    """Parse Windows event message to extract key-value pairs"""
    
    # Common patterns in Windows event messages
    patterns = {
        'account': r'Account Name:\s*(.+)',
        'domain': r'Account Domain:\s*(.+)',
        'logon_type': r'Logon Type:\s*(\d+)',
        'source_ip': r'Source Network Address:\s*(\S+)',
        'process': r'Process Name:\s*(.+)',
        'workstation': r'Workstation Name:\s*(.+)'
    }
    
    extracted = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            extracted[key] = match.group(1).strip()
    
    return extracted


class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, calls: int, period: int):
        """
        Args:
            calls: Number of calls allowed
            period: Time period in seconds
        """
        self.calls = calls
        self.period = period
        self.timestamps = []
    
    async def acquire(self):
        """Wait until a call can be made"""
        
        import time
        
        now = time.time()
        
        # Remove old timestamps
        self.timestamps = [
            ts for ts in self.timestamps
            if now - ts < self.period
        ]
        
        # Wait if at limit
        if len(self.timestamps) >= self.calls:
            sleep_time = self.period - (now - self.timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            # Remove oldest timestamp
            self.timestamps.pop(0)
        
        # Add new timestamp
        self.timestamps.append(time.time())


def get_event_description(event_id: int) -> str:
    """Get description for common Windows Event IDs"""
    
    descriptions = {
        # Security Events
        4624: "An account was successfully logged on",
        4625: "An account failed to log on",
        4634: "An account was logged off",
        4648: "A logon was attempted using explicit credentials",
        4672: "Special privileges assigned to new logon",
        4673: "A privileged service was called",
        4688: "A new process has been created",
        4689: "A process has exited",
        4720: "A user account was created",
        4722: "A user account was enabled",
        4723: "An attempt was made to change an account's password",
        4724: "An attempt was made to reset an account's password",
        4725: "A user account was disabled",
        4726: "A user account was deleted",
        4732: "A member was added to a security-enabled local group",
        4733: "A member was removed from a security-enabled local group",
        4740: "A user account was locked out",
        4767: "A user account was unlocked",
        4768: "A Kerberos authentication ticket (TGT) was requested",
        4769: "A Kerberos service ticket was requested",
        4771: "Kerberos pre-authentication failed",
        4776: "The domain controller attempted to validate credentials",
        
        # System Events
        1074: "System has been shutdown by a process/user",
        6005: "The Event log service was started",
        6006: "The Event log service was stopped",
        6008: "The previous system shutdown was unexpected",
        
        # Application Events
        1000: "Application Error",
        1001: "Application Hang",
        1002: "Application crashed"
    }
    
    return descriptions.get(event_id, f"Event ID {event_id}")


def validate_ip(ip: str) -> bool:
    """Validate IP address format"""
    
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    
    octets = ip.split('.')
    return all(0 <= int(octet) <= 255 for octet in octets)


def validate_hostname(hostname: str) -> bool:
    """Validate hostname format"""
    
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    return bool(re.match(pattern, hostname))


class PerformanceMonitor:
    """Monitor performance metrics"""
    
    def __init__(self):
        self.metrics = {}
    
    def record(self, metric: str, value: float):
        """Record a metric value"""
        
        if metric not in self.metrics:
            self.metrics[metric] = []
        self.metrics[metric].append(value)
    
    def get_stats(self, metric: str) -> dict:
        """Get statistics for a metric"""
        
        if metric not in self.metrics or not self.metrics[metric]:
            return {}
        
        values = self.metrics[metric]
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'total': sum(values)
        }
    
    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()
