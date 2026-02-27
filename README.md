# Headless Sentinel

**A lightweight, CLI-driven alternative to Splunk for Windows environments**

Headless Sentinel is a production-ready log aggregation and analysis tool designed specifically for Windows networks. It provides enterprise-grade log collection, analysis, and alerting without the overhead of a web GUI.

## 🚀 Features

### Core Capabilities
- **Remote Log Collection**: Asynchronously collect Windows Event Logs (System, Security, Application) from multiple machines using WinRM
- **High-Performance Storage**: DuckDB-based analytical engine for lightning-fast SQL queries
- **Proactive Alerting**: Real-time monitoring with Discord/Slack webhook integration
- **Automated Remediation**: Execute PowerShell scripts on target machines when threats are detected
- **Rich CLI Interface**: Color-coded, interactive command-line interface with live log tailing
- **Security Reports**: Generate comprehensive Markdown/HTML/JSON security posture reports

### Key Differentiators
- **Zero GUI Overhead**: Pure CLI-driven workflow
- **Windows-Native**: Built specifically for Windows environments
- **Lightweight**: Minimal resource footprint compared to traditional SIEM solutions
- **Fast Deployment**: Single Python application, no complex infrastructure
- **Secure by Design**: Credential encryption via Windows Credential Manager

## 📋 Prerequisites

### System Requirements
- **Operating System**: Windows 10/11 or Windows Server 2016+
- **Python**: 3.8 or higher
- **WinRM**: Enabled on all target machines

### Target Machine Configuration

Enable WinRM on machines you want to monitor:

```powershell
# Run as Administrator on each target machine
Enable-PSRemoting -Force
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
```

**Security Note**: For production environments, use HTTPS transport with certificate authentication.

## 🔧 Installation

### 1. Clone or Download

```bash
git clone https://github.com/yourorg/headless-sentinel.git
cd headless-sentinel
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
python main.py init
```

### 4. Configure Targets

Generate a sample configuration:

```bash
python main.py generate-config
```

Edit `config.yaml` and add your target machines.

### 5. Set Up Credentials (IMPORTANT)

**Never hardcode credentials in config.yaml!** Use one of these secure methods:

#### Option A: Environment Variables (Recommended)

```cmd
REM For each target machine
set SENTINEL_192_168_1_100_USERNAME=Administrator
set SENTINEL_192_168_1_100_PASSWORD=YourSecurePassword

REM Or use default credentials for all machines
set SENTINEL_DEFAULT_USERNAME=Administrator
set SENTINEL_DEFAULT_PASSWORD=YourSecurePassword
```

#### Option B: Windows Credential Manager (Most Secure)

```python
from config_manager import ConfigManager

config = ConfigManager()
config.set_credentials('192.168.1.100', 'Administrator', 'YourSecurePassword')
```

Credentials are encrypted and stored in Windows Credential Manager.

## 📖 Usage

### Basic Commands

#### Collect Logs Once

```bash
python main.py collect
```

#### Continuous Collection (Daemon Mode)

```bash
python main.py collect --continuous --interval 300
```

Collects logs every 5 minutes (300 seconds).

#### Query Logs

```bash
# Search for failed login attempts in the last hour
python main.py query -e 4625 -l 1h

# Search by severity
python main.py query -s error --last 24h

# Search by host
python main.py query --host 192.168.1.100

# Raw SQL query
python main.py query -q "SELECT * FROM logs WHERE event_id IN (4624, 4625) ORDER BY timestamp DESC"

# Export results to CSV
python main.py query -e 4625 --export failed_logins.csv
```

#### Live Log Tailing

```bash
# Tail all logs
python main.py tail -f

# Tail with filter
python main.py tail -f --filter "event_id=4625"

# Show last 100 lines
python main.py tail -n 100
```

#### Start Watcher (Alerting Daemon)

```bash
python main.py watch
```

Monitors logs in real-time and triggers alerts based on rules in `config.yaml`.

#### Generate Security Report

```bash
# Daily report (default)
python main.py report

# Weekly report
python main.py report -p 7d

# HTML format
python main.py report -f html -o security_report.html
```

#### Check System Status

```bash
python main.py status
```

### Advanced Usage

#### Custom Collection Interval

```bash
python main.py collect --continuous --interval 60
```

#### Multi-Target Collection

Edit `config.yaml`:

```yaml
targets:
  - ip: 192.168.1.100
    port: 5985
  - ip: 192.168.1.101
    port: 5985
  - ip: 192.168.1.102
    port: 5985
```

#### Custom Alert Rules

Edit `config.yaml`:

```yaml
alerts:
  rules:
    - name: Brute Force Detection
      event_ids: [4625]
      threshold: 10
      actions:
        - type: webhook
          url: https://discord.com/api/webhooks/YOUR_WEBHOOK
          type_hint: discord
        - type: remediation
          script: |
            # Block suspicious IP
            netsh advfirewall firewall add rule name="Block Attacker" dir=in action=block remoteip=$SOURCE_IP
```

## 🔔 Alert Actions

### Webhook Notifications

#### Discord

```yaml
- type: webhook
  url: https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
  type_hint: discord
```

#### Slack

```yaml
- type: webhook
  url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
  type_hint: slack
```

### Automated Remediation

```yaml
- type: remediation
  script: |
    # Unlock user account
    net user $USERNAME /unlock
    
    # Disable compromised account
    net user $USERNAME /active:no
    
    # Restart service
    Restart-Service -Name $SERVICE_NAME
```

**Security Note**: Remediation scripts run with the privileges of the WinRM connection. Use with caution.

## 📊 Database Management

### Query Performance

DuckDB provides exceptional query performance:

- **Columnar storage**: Optimized for analytical queries
- **Automatic indexing**: Fast lookups on timestamp, event_id, computer
- **SQL interface**: Full SQL support with aggregations, JOINs, window functions

### Example Queries

```sql
-- Top 10 computers by failed login attempts
SELECT computer, COUNT(*) as failed_logins
FROM logs
WHERE event_id = 4625 AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
GROUP BY computer
ORDER BY failed_logins DESC
LIMIT 10;

-- Security events timeline
SELECT 
    DATE_TRUNC('hour', timestamp) as hour,
    COUNT(*) as event_count,
    SUM(CASE WHEN level = 'Critical' THEN 1 ELSE 0 END) as critical
FROM logs
WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour;

-- Failed vs successful logins
SELECT 
    computer,
    SUM(CASE WHEN event_id = 4625 THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN event_id = 4624 THEN 1 ELSE 0 END) as successful
FROM logs
GROUP BY computer;
```

### Database Maintenance

```python
from database import DatabaseManager

db = DatabaseManager()

# Optimize database
db.vacuum()

# Export to Parquet
db.export_to_parquet('backup.parquet')

# Delete old logs (older than 90 days)
db.delete_old_logs(90)

# Create backup
db.create_backup('sentinel_backup.duckdb')
```

## 🔒 Security Best Practices

### Credential Management

1. **Never** commit credentials to version control
2. Use Windows Credential Manager (keyring) for production
3. Rotate credentials regularly
4. Use service accounts with minimal required privileges

### Network Security

1. Use HTTPS transport for WinRM in production
2. Implement certificate-based authentication
3. Restrict WinRM access to specific IP ranges
4. Enable Windows Firewall rules

### Access Control

1. Run Headless Sentinel as a dedicated service account
2. Limit file system permissions on database and config files
3. Audit access to the Sentinel machine
4. Implement log retention policies

## 📁 Project Structure

```
headless-sentinel/
├── main.py              # CLI entry point
├── collector.py         # Remote log collection
├── analyzer.py          # Query engine & alerting
├── database.py          # DuckDB interface
├── config_manager.py    # Configuration & credentials
├── utils.py             # Utilities & helpers
├── config.yaml          # Configuration file
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## 🐛 Troubleshooting

### WinRM Connection Failed

**Problem**: `Failed to connect to 192.168.1.100`

**Solution**:
1. Verify WinRM is enabled on target: `winrm quickconfig`
2. Check firewall rules: `Test-NetConnection -ComputerName 192.168.1.100 -Port 5985`
3. Verify credentials are correct
4. Check network connectivity

### No Logs Collected

**Problem**: Collection completes but 0 logs stored

**Solution**:
1. Check event log permissions on target machine
2. Verify time range (`hours_back` in config)
3. Check if events exist: `Get-WinEvent -LogName Security -MaxEvents 10`
4. Review logs for errors: `python main.py collect --verbose`

### High Memory Usage

**Problem**: Python process consuming excessive memory

**Solution**:
1. Reduce `max_events` in config.yaml
2. Implement log retention: `db.delete_old_logs(30)`
3. Collect from fewer hosts simultaneously
4. Increase collection interval

### Query Performance Issues

**Problem**: Queries are slow

**Solution**:
1. Run `db.vacuum()` to optimize
2. Add indexes if needed
3. Use time-based filters in queries
4. Consider archiving old data

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Follow PEP-8 coding standards
4. Add tests for new functionality
5. Update documentation
6. Submit a pull request

## 📜 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- Built with [DuckDB](https://duckdb.org/) - Fast analytical database
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [pywinrm](https://github.com/diyan/pywinrm) - WinRM client library

## 📞 Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Email: security@yourcompany.com
- Documentation: https://docs.yourcompany.com/sentinel

## 🗺️ Roadmap

- [ ] Web-based dashboard (optional)
- [ ] Multi-platform support (Linux/macOS targets)
- [ ] Machine learning anomaly detection
- [ ] Integration with other SIEM tools
- [ ] Custom parser plugins
- [ ] Distributed deployment support

---

**Headless Sentinel** - Enterprise-grade log management without the enterprise overhead.
