# Headless Sentinel - Deployment Guide

## Quick Start (5 Minutes)

### Step 1: Install Headless Sentinel

```bash
# Clone repository
git clone https://github.com/yourorg/headless-sentinel.git
cd headless-sentinel

# Install dependencies
pip install -r requirements.txt

# Initialize database
python main.py init
```

### Step 2: Configure Target Machines

On each Windows machine you want to monitor, run as Administrator:

```powershell
# Download and run setup script
.\setup_target.ps1
```

### Step 3: Configure Sentinel

```bash
# Generate configuration file
python main.py generate-config

# Edit config.yaml and add your target IPs
notepad config.yaml
```

### Step 4: Set Credentials

```cmd
# Set environment variables for each target
set SENTINEL_192_168_1_100_USERNAME=Administrator
set SENTINEL_192_168_1_100_PASSWORD=YourPassword

# Or use default credentials
set SENTINEL_DEFAULT_USERNAME=Administrator
set SENTINEL_DEFAULT_PASSWORD=YourPassword
```

### Step 5: Test Collection

```bash
# Run one-time collection
python main.py collect

# Check status
python main.py status

# Query recent logs
python main.py query -l 1h
```

## Production Deployment

### Architecture

```
┌─────────────────────┐
│  Sentinel Server    │
│  (Central Machine)  │
│                     │
│  ┌───────────────┐  │
│  │ Headless      │  │
│  │ Sentinel      │  │
│  └───────┬───────┘  │
│          │          │
│  ┌───────▼───────┐  │
│  │ DuckDB        │  │
│  └───────────────┘  │
└──────────┬──────────┘
           │
           │ WinRM (5985/5986)
           │
    ┌──────┴──────┬──────────┬──────────┐
    │             │          │          │
┌───▼───┐   ┌────▼───┐  ┌───▼───┐  ┌───▼───┐
│ Host1 │   │ Host2  │  │ Host3 │  │ HostN │
│       │   │        │  │       │  │       │
└───────┘   └────────┘  └───────┘  └───────┘
```

### 1. Server Setup

#### Hardware Requirements
- **CPU**: 2+ cores
- **RAM**: 4GB+ (8GB recommended for large deployments)
- **Disk**: 50GB+ SSD (faster I/O improves query performance)
- **Network**: 100Mbps+ for large-scale deployments

#### Software Requirements
- Windows Server 2016+ or Windows 10/11
- Python 3.8+
- Network access to all target machines

### 2. Network Configuration

#### Firewall Rules

On Sentinel server:
```powershell
# Allow outbound WinRM
New-NetFirewallRule -DisplayName "Sentinel-WinRM-Out" `
                    -Direction Outbound `
                    -Action Allow `
                    -Protocol TCP `
                    -RemotePort 5985,5986
```

On target machines:
```powershell
# Use setup_target.ps1 script
.\setup_target.ps1
```

#### DNS Configuration
For easier management, configure DNS records for target machines:
- `server1.company.local` → 192.168.1.100
- `server2.company.local` → 192.168.1.101

### 3. Security Hardening

#### Use HTTPS Transport

Generate certificates and configure HTTPS:

```powershell
# On target machine
$cert = New-SelfSignedCertificate -DnsName "server1.company.local" `
                                  -CertStoreLocation Cert:\LocalMachine\My

winrm create winrm/config/Listener?Address=*+Transport=HTTPS `
             "@{Hostname=`"server1.company.local`"; CertificateThumbprint=`"$($cert.Thumbprint)`"}"

# Update config.yaml
# targets:
#   - ip: server1.company.local
#     port: 5986
#     transport: ssl
```

#### Service Account

Create dedicated service account with minimal privileges:

```powershell
# Create service account
$password = Read-Host "Enter password" -AsSecureString
New-LocalUser -Name "SentinelService" -Password $password -PasswordNeverExpires

# Grant necessary permissions
Add-LocalGroupMember -Group "Event Log Readers" -Member "SentinelService"
Add-LocalGroupMember -Group "Remote Management Users" -Member "SentinelService"
```

Update config to use service account credentials.

### 4. Run as Windows Service

Create a Windows service to run Sentinel continuously.

#### Create Service Script (sentinel_service.py)

```python
import win32serviceutil
import win32service
import win32event
import servicemanager
import subprocess
import sys

class SentinelService(win32serviceutil.ServiceFramework):
    _svc_name_ = "HeadlessSentinel"
    _svc_display_name_ = "Headless Sentinel Log Collector"
    _svc_description_ = "Collects and analyzes Windows Event Logs"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None
    
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.process:
            self.process.terminate()
    
    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()
    
    def main(self):
        # Run collector in continuous mode
        self.process = subprocess.Popen(
            [sys.executable, "main.py", "collect", "--continuous", "--interval", "300"],
            cwd="C:\\Path\\To\\Headless-Sentinel"
        )
        
        # Wait for stop signal
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(SentinelService)
```

#### Install Service

```cmd
# Install service
python sentinel_service.py install

# Start service
python sentinel_service.py start

# Check status
python sentinel_service.py status
```

### 5. Scheduled Reporting

Use Windows Task Scheduler to generate daily reports:

```powershell
$action = New-ScheduledTaskAction -Execute "python" `
                                  -Argument "main.py report -p 24h" `
                                  -WorkingDirectory "C:\Path\To\Headless-Sentinel"

$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM

Register-ScheduledTask -TaskName "Sentinel Daily Report" `
                       -Action $action `
                       -Trigger $trigger `
                       -Description "Generate daily security report"
```

### 6. Monitoring and Maintenance

#### Database Maintenance

Schedule weekly database optimization:

```python
# maintenance.py
from database import DatabaseManager

db = DatabaseManager()

# Vacuum database
db.vacuum()

# Delete old logs (90 days)
db.delete_old_logs(90)

# Create backup
from datetime import datetime
backup_name = f"backup_{datetime.now().strftime('%Y%m%d')}.duckdb"
db.create_backup(backup_name)

print(f"Maintenance complete. Backup: {backup_name}")
```

Schedule in Task Scheduler:
```powershell
$action = New-ScheduledTaskAction -Execute "python" `
                                  -Argument "maintenance.py" `
                                  -WorkingDirectory "C:\Path\To\Headless-Sentinel"

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 2:00AM

Register-ScheduledTask -TaskName "Sentinel Maintenance" `
                       -Action $action `
                       -Trigger $trigger
```

#### Health Monitoring

Monitor Sentinel health:

```python
# health_check.py
from database import DatabaseManager
from datetime import datetime, timedelta

db = DatabaseManager()
stats = db.get_table_stats()

# Check if logs are recent
latest = stats.get('latest_log')
if latest:
    latest_dt = datetime.fromisoformat(str(latest))
    age = datetime.utcnow() - latest_dt
    
    if age > timedelta(hours=2):
        print(f"WARNING: No logs in {age.total_seconds()/3600:.1f} hours")
        # Send alert
    else:
        print(f"OK: Latest log {age.total_seconds()/60:.0f} minutes ago")

# Check database size
size_mb = stats.get('size_mb', 0)
if size_mb > 10000:  # 10 GB
    print(f"WARNING: Database size is {size_mb:.0f} MB")
    # Send alert
else:
    print(f"OK: Database size is {size_mb:.0f} MB")
```

### 7. Scaling Considerations

#### Large Deployments (100+ Hosts)

1. **Parallel Collection**: Increase `concurrent_hosts` in config:
```yaml
collection:
  concurrent_hosts: 50
```

2. **Distribute Load**: Run multiple Sentinel instances:
```yaml
# sentinel1_config.yaml - Monitors hosts 1-50
targets:
  - ip: 192.168.1.1
  - ip: 192.168.1.2
  ...

# sentinel2_config.yaml - Monitors hosts 51-100
targets:
  - ip: 192.168.1.51
  - ip: 192.168.1.52
  ...
```

3. **Database Partitioning**: Archive old data to Parquet:
```python
# Archive logs older than 30 days
db.export_to_parquet(
    'archive_202401.parquet',
    filters="timestamp < '2024-02-01'"
)
db.delete_old_logs(30)
```

### 8. Disaster Recovery

#### Backup Strategy

1. **Database Backups**: Daily automated backups
2. **Configuration Backups**: Version control config.yaml
3. **Credential Backups**: Document credential recovery process

#### Recovery Procedure

```bash
# 1. Install Sentinel on new machine
pip install -r requirements.txt

# 2. Restore configuration
copy config.yaml.backup config.yaml

# 3. Restore database
copy sentinel_backup.duckdb sentinel.duckdb

# 4. Restore credentials
# Follow credential setup procedure

# 5. Test
python main.py status
python main.py query -l 24h
```

## Troubleshooting

### Common Issues

#### Issue: "Failed to connect"
- Check WinRM is enabled: `winrm quickconfig`
- Test connectivity: `Test-NetConnection -Port 5985`
- Verify credentials

#### Issue: "Permission denied"
- Check user is in "Event Log Readers" group
- Verify "Remote Management Users" membership
- Check Event Log permissions

#### Issue: "High CPU usage"
- Reduce collection frequency
- Limit `max_events` in config
- Add indexes to database

#### Issue: "Database locked"
- Close all connections: `db.close()`
- Check for zombie processes
- Restart Sentinel service

## Support

For additional help:
- Documentation: https://docs.yourcompany.com/sentinel
- Issues: https://github.com/yourorg/headless-sentinel/issues
- Email: support@yourcompany.com
