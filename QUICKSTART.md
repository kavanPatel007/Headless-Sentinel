# Headless Sentinel - Quick Start Guide

Get up and running with Headless Sentinel in 5 minutes!

## Prerequisites

- Windows 10/11 or Windows Server 2016+
- Python 3.8+
- Administrator access on target machines

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Initialize Database

```bash
python main.py init
```

## Configuration

### 1. Setup Target Machines

On each Windows machine you want to monitor, run as Administrator:

```powershell
# Enable WinRM
Enable-PSRemoting -Force

# Configure WinRM (Development only - use HTTPS in production!)
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true

# Allow WinRM through firewall
Enable-NetFirewallRule -DisplayGroup "Windows Remote Management"
```

Or use the provided setup script:
```powershell
.\setup_target.ps1
```

### 2. Generate Configuration

```bash
python main.py generate-config
```

This creates `config.yaml`. Edit it to add your target machines:

```yaml
targets:
  - ip: 192.168.1.100
    port: 5985
  - ip: 192.168.1.101
    port: 5985
```

### 3. Set Credentials

**Method 1 - Environment Variables (Recommended)**

```cmd
set SENTINEL_DEFAULT_USERNAME=Administrator
set SENTINEL_DEFAULT_PASSWORD=YourPassword
```

**Method 2 - Per-host Credentials**

```cmd
set SENTINEL_192_168_1_100_USERNAME=admin
set SENTINEL_192_168_1_100_PASSWORD=pass123
```

**Method 3 - Keyring (Most Secure)**

```python
from config_manager import ConfigManager
config = ConfigManager()
config.set_credentials('192.168.1.100', 'username', 'password')
```

## Usage

### Collect Logs (One-time)

```bash
python main.py collect
```

### Collect Logs (Continuous)

```bash
python main.py collect --continuous --interval 300
```

Collects logs every 5 minutes.

### Query Logs

```bash
# Failed login attempts
python main.py query -e 4625 -l 24h

# All errors
python main.py query -s error

# Raw SQL
python main.py query -q "SELECT * FROM logs WHERE event_id = 4625 LIMIT 10"
```

### Live Log Tail

```bash
python main.py tail -f
```

Press Ctrl+C to stop.

### Start Watcher (Alerts)

```bash
python main.py watch
```

### Generate Report

```bash
python main.py report
```

Creates `security_report.md`.

### Check Status

```bash
python main.py status
```

## Common Event IDs

| Event ID | Description |
|----------|-------------|
| 4624 | Successful login |
| 4625 | Failed login |
| 4648 | Login with explicit credentials |
| 4672 | Special privileges assigned |
| 4720 | User account created |
| 4732 | User added to security group |
| 4740 | Account locked out |

## Alert Configuration

Edit `config.yaml` to add webhook alerts:

```yaml
alerts:
  rules:
    - name: Failed Login Attempts
      event_ids: [4625]
      threshold: 5
      actions:
        - type: webhook
          url: https://discord.com/api/webhooks/YOUR_WEBHOOK
          type_hint: discord
```

Get Discord webhook: Server Settings → Integrations → Webhooks → New Webhook

## Example Queries

### Failed logins by computer
```bash
python main.py query -q "SELECT computer, COUNT(*) as count FROM logs WHERE event_id = 4625 GROUP BY computer"
```

### Recent critical events
```bash
python main.py query -s critical -l 24h
```

### Export to CSV
```bash
python main.py query -e 4625 --export failed_logins.csv
```

## Troubleshooting

### "Failed to connect"

**Solution:**
1. Check WinRM is running: `Get-Service WinRM`
2. Test connection: `Test-WSMan -ComputerName 192.168.1.100`
3. Verify credentials are correct

### "No logs collected"

**Solution:**
1. Check target machine has events: `Get-WinEvent -LogName Security -MaxEvents 10`
2. Verify time range in config (`hours_back: 1`)
3. Check user has permission to read event logs

### "Permission denied"

**Solution:**
1. Add user to "Event Log Readers" group
2. Add user to "Remote Management Users" group

## Next Steps

- **Production Deployment**: See `DEPLOYMENT.md`
- **Full Documentation**: See `README.md`
- **Advanced Configuration**: Edit `config.yaml`

## Support

- GitHub Issues: https://github.com/yourorg/headless-sentinel/issues
- Documentation: https://docs.yourcompany.com/sentinel
- Email: support@yourcompany.com

## Security Reminder

⚠️ **IMPORTANT**: The quick start uses unencrypted WinRM for simplicity. 

For production:
- Use HTTPS transport (port 5986)
- Use certificate-based authentication
- Never hardcode credentials in config files
- Use Windows Credential Manager (keyring)
- Implement least-privilege access

See `DEPLOYMENT.md` for production security setup.
