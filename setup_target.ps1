# Headless Sentinel - Target Machine Setup Script
# Run this script as Administrator on each Windows machine you want to monitor

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Headless Sentinel - Target Setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/5] Configuring WinRM..." -ForegroundColor Green

# Enable PowerShell Remoting
try {
    Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null
    Write-Host "  ✓ PSRemoting enabled" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to enable PSRemoting: $_" -ForegroundColor Red
    exit 1
}

Write-Host "[2/5] Configuring WinRM Service..." -ForegroundColor Green

# Set WinRM service to automatic start
Set-Service -Name WinRM -StartupType Automatic
Start-Service -Name WinRM

# Configure WinRM settings
winrm quickconfig -quiet

# Basic authentication (WARNING: Use HTTPS in production!)
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true

# Allow unencrypted traffic (WARNING: Development only!)
# In production, use HTTPS with certificates
$allowUnencrypted = Read-Host "Allow unencrypted traffic? (NOT recommended for production) [y/N]"
if ($allowUnencrypted -eq 'y' -or $allowUnencrypted -eq 'Y') {
    Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true
    winrm set winrm/config/service '@{AllowUnencrypted="true"}' | Out-Null
    Write-Host "  ⚠ Unencrypted traffic enabled (NOT recommended for production)" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ Unencrypted traffic disabled (HTTPS required)" -ForegroundColor Green
}

Write-Host "[3/5] Configuring Firewall..." -ForegroundColor Green

# Allow WinRM through firewall
try {
    Enable-NetFirewallRule -DisplayGroup "Windows Remote Management" -ErrorAction SilentlyContinue
    
    # Add explicit rule if needed
    $ruleName = "WinRM-HTTP-In-TCP"
    $existingRule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    
    if (-not $existingRule) {
        New-NetFirewallRule -Name $ruleName `
                           -DisplayName "Windows Remote Management (HTTP-In)" `
                           -Profile Any `
                           -Direction Inbound `
                           -Action Allow `
                           -Protocol TCP `
                           -LocalPort 5985 | Out-Null
        Write-Host "  ✓ Firewall rule created" -ForegroundColor Green
    } else {
        Write-Host "  ✓ Firewall rule already exists" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ Failed to configure firewall: $_" -ForegroundColor Red
}

Write-Host "[4/5] Configuring Event Log Access..." -ForegroundColor Green

# Ensure Event Log service is running
Start-Service -Name EventLog -ErrorAction SilentlyContinue
Set-Service -Name EventLog -StartupType Automatic

# Set Event Log permissions (optional)
$setPermissions = Read-Host "Configure Event Log permissions for monitoring user? [y/N]"
if ($setPermissions -eq 'y' -or $setPermissions -eq 'Y') {
    $username = Read-Host "Enter username for Event Log access (e.g., DOMAIN\ServiceAccount)"
    
    try {
        # Grant read access to Event Logs
        wevtutil sl Security /ca:O:BAG:SYD:(A;;0x1;;;BA)(A;;0x1;;;SY)(A;;0x1;;;$username)
        wevtutil sl System /ca:O:BAG:SYD:(A;;0x1;;;BA)(A;;0x1;;;SY)(A;;0x1;;;$username)
        wevtutil sl Application /ca:O:BAG:SYD:(A;;0x1;;;BA)(A;;0x1;;;SY)(A;;0x1;;;$username)
        Write-Host "  ✓ Event Log permissions configured for $username" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Failed to set permissions: $_" -ForegroundColor Red
    }
} else {
    Write-Host "  ⊘ Skipped permission configuration" -ForegroundColor Yellow
}

Write-Host "[5/5] Testing Configuration..." -ForegroundColor Green

# Test WinRM
try {
    $testResult = Test-WSMan -ComputerName localhost -ErrorAction Stop
    Write-Host "  ✓ WinRM is responding correctly" -ForegroundColor Green
} catch {
    Write-Host "  ✗ WinRM test failed: $_" -ForegroundColor Red
    exit 1
}

# Display configuration summary
Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Configuration Summary" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

$config = winrm get winrm/config

Write-Host ""
Write-Host "WinRM Service: " -NoNewline
if ((Get-Service WinRM).Status -eq 'Running') {
    Write-Host "Running ✓" -ForegroundColor Green
} else {
    Write-Host "Not Running ✗" -ForegroundColor Red
}

Write-Host "WinRM Port: 5985 (HTTP)"

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Test connection from Sentinel machine:"
Write-Host "     Test-WSMan -ComputerName $env:COMPUTERNAME"
Write-Host ""
Write-Host "  2. Configure credentials on Sentinel machine:"
Write-Host "     set SENTINEL_${env:COMPUTERNAME}_USERNAME=YourUsername"
Write-Host "     set SENTINEL_${env:COMPUTERNAME}_PASSWORD=YourPassword"
Write-Host ""
Write-Host "  3. Add this machine to config.yaml:"
Write-Host "     targets:"
Write-Host "       - ip: $(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '127.*'} | Select-Object -First 1 -ExpandProperty IPAddress)"
Write-Host "         port: 5985"
Write-Host ""

Write-Host "Setup Complete! ✓" -ForegroundColor Green
Write-Host ""

# Optional: Create a test user for Sentinel
$createUser = Read-Host "Create a dedicated service account for Sentinel? [y/N]"
if ($createUser -eq 'y' -or $createUser -eq 'Y') {
    $username = Read-Host "Enter username (e.g., SentinelService)"
    $password = Read-Host "Enter password" -AsSecureString
    
    try {
        # Create user
        New-LocalUser -Name $username -Password $password -FullName "Headless Sentinel Service Account" `
                      -Description "Service account for Headless Sentinel log collection" `
                      -PasswordNeverExpires -UserMayNotChangePassword | Out-Null
        
        # Add to Event Log Readers group
        Add-LocalGroupMember -Group "Event Log Readers" -Member $username -ErrorAction SilentlyContinue
        
        # Add to Remote Management Users group
        Add-LocalGroupMember -Group "Remote Management Users" -Member $username -ErrorAction SilentlyContinue
        
        Write-Host "  ✓ Service account created: $username" -ForegroundColor Green
        Write-Host "  ✓ Added to Event Log Readers group" -ForegroundColor Green
        Write-Host "  ✓ Added to Remote Management Users group" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Failed to create user: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "SECURITY REMINDER:" -ForegroundColor Red
Write-Host "  • This configuration allows basic authentication" -ForegroundColor Yellow
Write-Host "  • For production, use HTTPS with certificate authentication" -ForegroundColor Yellow
Write-Host "  • Restrict WinRM access to specific IP addresses" -ForegroundColor Yellow
Write-Host "  • Use strong passwords and rotate them regularly" -ForegroundColor Yellow
Write-Host ""
