import winrm
import time
import os

target_ip = "xy.xy.xy.xy" #replace xy with target machine ip addess
username = os.getenv('SENTINEL_DEFAULT_USERNAME', 'username') # replace username with target machine username
password = os.getenv('SENTINEL_DEFAULT_PASSWORD', 'password') # replace password with target machine password

# Very simple test
simple_script = """
Write-Output "Test starting"
Get-Date
Write-Output "Test complete"
"""

print(f"Testing basic WinRM speed to {target_ip}...")

try:
    endpoint = f'http://{target_ip}:5985/wsman'
    session = winrm.Session(
        endpoint,
        auth=(username, password),
        transport='ntlm',
        server_cert_validation='ignore'
    )
    
    start = time.time()
    result = session.run_ps(simple_script)
    elapsed = time.time() - start
    
    print(f"✓ Basic command took {elapsed:.2f} seconds")
    print(f"Output: {result.std_out.decode('utf-8')}")
    
    # Now test a small event log query
    small_query = """
    $events = Get-WinEvent -LogName System -MaxEvents 10 -ErrorAction SilentlyContinue
    Write-Output "Found $($events.Count) events"
    """
    
    print("\nTesting small event query...")
    start = time.time()
    result = session.run_ps(small_query)
    elapsed = time.time() - start
    
    print(f"✓ Small query took {elapsed:.2f} seconds")
    print(f"Output: {result.std_out.decode('utf-8')}")
    
except Exception as e:

    print(f"✗ Error: {e}")
