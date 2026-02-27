"""
Headless Sentinel - Configuration Manager Module

Handles configuration loading and secure credential management.
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path

import yaml
import keyring

from utils import setup_logging

logger = setup_logging()


class ConfigManager:
    """Configuration and credential manager"""
    
    SERVICE_NAME = "HeadlessSentinel"
    
    def __init__(self, config_path: str = 'config.yaml'):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from YAML file"""
        
        config_file = Path(self.config_path)
        
        if not config_file.exists():
            logger.warning(f"Config file not found: {self.config_path}")
            logger.info("Using default configuration")
            self.config = self._get_default_config()
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}
            logger.info(f"Configuration loaded from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = self._get_default_config()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default
    
    def get_credentials(self, target: str) -> Dict[str, str]:
        """Get credentials for a target host"""
        
        # First, try keyring
        username = keyring.get_password(self.SERVICE_NAME, f"{target}_username")
        password = keyring.get_password(self.SERVICE_NAME, f"{target}_password")
        
        if username and password:
            return {'username': username, 'password': password}
        
        # Fall back to environment variables
        username = os.getenv(f"SENTINEL_{target.replace('.', '_')}_USERNAME")
        password = os.getenv(f"SENTINEL_{target.replace('.', '_')}_PASSWORD")
        
        if username and password:
            return {'username': username, 'password': password}
        
        # Fall back to config file (not recommended for production)
        for target_config in self.config.get('targets', []):
            if target_config.get('ip') == target:
                if 'credentials' in target_config:
                    logger.warning(
                        f"Using credentials from config file for {target}. "
                        "Consider using keyring or environment variables."
                    )
                    return target_config['credentials']
        
        # Try default credentials
        default_username = os.getenv('SENTINEL_DEFAULT_USERNAME')
        default_password = os.getenv('SENTINEL_DEFAULT_PASSWORD')
        
        if default_username and default_password:
            logger.warning(f"Using default credentials for {target}")
            return {'username': default_username, 'password': default_password}
        
        raise ValueError(f"No credentials found for {target}")
    
    def set_credentials(self, target: str, username: str, password: str):
        """Store credentials securely in keyring"""
        
        try:
            keyring.set_password(self.SERVICE_NAME, f"{target}_username", username)
            keyring.set_password(self.SERVICE_NAME, f"{target}_password", password)
            logger.info(f"Credentials stored for {target}")
        except Exception as e:
            logger.error(f"Failed to store credentials: {e}")
            raise
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        
        return {
            'database': {
                'path': 'sentinel.duckdb',
                'retention_days': 90
            },
            'collection': {
                'log_types': ['System', 'Security', 'Application'],
                'hours_back': 1,
                'max_events': 10000
            },
            'targets': [],
            'alerts': {
                'enabled': True,
                'check_interval': 60,
                'rules': [
                    {
                        'name': 'Failed Login Attempts',
                        'event_ids': [4625],
                        'threshold': 5,
                        'actions': []
                    },
                    {
                        'name': 'Critical Errors',
                        'severity': 'Critical',
                        'threshold': 1,
                        'actions': []
                    }
                ]
            },
            'reporting': {
                'enabled': True,
                'schedule': '0 8 * * *',  # Daily at 8 AM
                'format': 'markdown'
            }
        }
    
    @staticmethod
    def generate_sample_config(output_path: str = 'config.yaml'):
        """Generate a sample configuration file"""
        
        sample_config = {
            'database': {
                'path': 'sentinel.duckdb',
                'retention_days': 90
            },
            'collection': {
                'log_types': ['System', 'Security', 'Application'],
                'hours_back': 1,
                'max_events': 10000,
                'concurrent_hosts': 10
            },
            'targets': [
                {
                    'ip': '192.168.1.100',
                    'port': 5985,
                    'transport': 'ntlm',
                    'timeout': 30,
                    # NOTE: Do not store credentials here in production!
                    # Use keyring or environment variables instead.
                    # See README for secure credential management.
                }
            ],
            'alerts': {
                'enabled': True,
                'check_interval': 60,
                'rules': [
                    {
                        'name': 'Failed Login Attempts',
                        'event_ids': [4625],
                        'threshold': 5,
                        'actions': [
                            {
                                'type': 'webhook',
                                'url': 'https://discord.com/api/webhooks/YOUR_WEBHOOK',
                                'type_hint': 'discord'
                            }
                        ]
                    },
                    {
                        'name': 'Privilege Escalation',
                        'event_ids': [4672, 4673],
                        'threshold': 1,
                        'actions': [
                            {
                                'type': 'webhook',
                                'url': 'https://hooks.slack.com/services/YOUR_WEBHOOK',
                                'type_hint': 'slack'
                            }
                        ]
                    },
                    {
                        'name': 'Account Lockout',
                        'event_ids': [4740],
                        'threshold': 1,
                        'actions': [
                            {
                                'type': 'remediation',
                                'script': 'net user $USERNAME /unlock'
                            }
                        ]
                    },
                    {
                        'name': 'Critical System Errors',
                        'severity': 'Critical',
                        'threshold': 1,
                        'actions': [
                            {
                                'type': 'webhook',
                                'url': 'YOUR_NOTIFICATION_URL'
                            }
                        ]
                    }
                ]
            },
            'reporting': {
                'enabled': True,
                'schedule': '0 8 * * *',
                'format': 'markdown',
                'output_dir': './reports'
            }
        }
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    sample_config,
                    f,
                    default_flow_style=False,
                    sort_keys=False
                )
            logger.info(f"Sample configuration generated: {output_path}")
        except Exception as e:
            logger.error(f"Failed to generate config: {e}")
            raise
