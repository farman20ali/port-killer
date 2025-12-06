#!/usr/bin/env python3
"""
kport - Cross-platform port inspector and killer
A simple command-line tool to inspect and kill processes using specific ports
"""
import argparse
import os
import platform
import subprocess
import sys
import re


# ANSI color codes
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def colorize(text, color):
    """Add color to text if terminal supports it"""
    if platform.system() == "Windows":
        # Enable ANSI colors on Windows 10+
        os.system("")
    return f"{color}{text}{Colors.RESET}"


def run(cmd):
    """Execute shell command and return output"""
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return ""
    except Exception as e:
        print(colorize(f"Error executing command: {e}", Colors.RED))
        return ""


def validate_port(port):
    """Validate if port number is in valid range"""
    if not (1 <= port <= 65535):
        print(colorize(f"Error: Port {port} is not valid. Port must be between 1 and 65535.", Colors.RED))
        sys.exit(1)


def parse_port_range(port_range):
    """Parse port range string (e.g., '3000-3010') into list of ports"""
    try:
        if '-' in port_range:
            start, end = port_range.split('-')
            start_port = int(start.strip())
            end_port = int(end.strip())
            
            if start_port > end_port:
                print(colorize(f"Error: Invalid range {port_range}. Start port must be less than end port.", Colors.RED))
                sys.exit(1)
            
            if end_port - start_port > 1000:
                print(colorize(f"Error: Range too large ({end_port - start_port} ports). Maximum 1000 ports allowed.", Colors.RED))
                sys.exit(1)
            
            ports = list(range(start_port, end_port + 1))
            for port in ports:
                validate_port(port)
            return ports
        else:
            port = int(port_range)
            validate_port(port)
            return [port]
    except ValueError:
        print(colorize(f"Error: Invalid port or range format: {port_range}", Colors.RED))
        sys.exit(1)


def find_pid(port):
    """Find process ID using given port"""
    system = platform.system()

    if system == "Windows":
        out = run(f"netstat -ano | findstr :{port}")
        if not out:
            return None, None
        
        # Parse the first line (could be multiple connections)
        lines = out.strip().split('\n')
        for line in lines:
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                proc_info = run(f'tasklist /FI "PID eq {pid}" /FO LIST')
                return pid, proc_info
        
        return None, None

    else:  # Linux, Ubuntu, macOS
        out = run(f"lsof -t -i:{port}")
        if not out:
            return None, None
        
        pid = out.strip().split('\n')[0]  # Get first PID if multiple
        proc_info = run(f"ps -p {pid} -o pid,user,command")
        return pid, proc_info


def list_all_ports():
    """List all listening ports and their processes"""
    system = platform.system()
    
    print(colorize("\n📋 Listing all active ports...\n", Colors.CYAN + Colors.BOLD))

    if system == "Windows":
        out = run("netstat -ano | findstr LISTENING")
        if not out:
            print(colorize("No listening ports found.", Colors.YELLOW))
            return
        
        print(colorize(f"{'Protocol':<10} {'Local Address':<25} {'State':<15} {'PID':<10}", Colors.BOLD))
        print("─" * 70)
        
        for line in out.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 5:
                protocol = parts[0]
                local_addr = parts[1]
                state = parts[3]
                pid = parts[4]
                print(f"{protocol:<10} {local_addr:<25} {state:<15} {pid:<10}")

    else:  # Linux, Ubuntu, macOS
        out = run("lsof -i -P -n | grep LISTEN")
        if not out:
            print(colorize("No listening ports found.", Colors.YELLOW))
            return
        
        print(colorize(f"{'Command':<20} {'PID':<10} {'User':<15} {'Address':<30}", Colors.BOLD))
        print("─" * 80)
        
        for line in out.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 9:
                command = parts[0]
                pid = parts[1]
                user = parts[2]
                address = parts[8]
                print(f"{command:<20} {pid:<10} {user:<15} {address:<30}")


def find_pids_by_process_name(process_name):
    """Find all PIDs matching a process name"""
    system = platform.system()
    pids = []

    if system == "Windows":
        out = run(f'tasklist /FI "IMAGENAME eq {process_name}*" /FO CSV /NH')
        if out:
            for line in out.strip().split('\n'):
                parts = line.replace('"', '').split(',')
                if len(parts) >= 2:
                    try:
                        pid = parts[1]
                        pids.append(pid)
                    except (ValueError, IndexError):
                        continue
    else:  # Linux, Ubuntu, macOS
        out = run(f"pgrep -f {process_name}")
        if out:
            pids = [pid.strip() for pid in out.strip().split('\n') if pid.strip()]
    
    return pids


def get_process_name(pid):
    """Get process name from PID"""
    system = platform.system()
    
    if system == "Windows":
        out = run(f'tasklist /FI "PID eq {pid}" /FO CSV /NH')
        if out:
            parts = out.strip().split(',')[0].replace('"', '')
            return parts
    else:
        out = run(f"ps -p {pid} -o comm=")
        if out:
            return out.strip()
    
    return "Unknown"


def find_ports_by_process_name(process_name):
    """Find all ports used by processes matching a name"""
    system = platform.system()
    process_port_map = []  # List of tuples: (pid, process_name, port)
    
    if system == "Windows":
        # Get all PIDs matching the process name
        pids = find_pids_by_process_name(process_name)
        
        if pids:
            # For each PID, find what ports it's using
            for pid in pids:
                out = run(f"netstat -ano | findstr {pid}")
                if out:
                    proc_name = get_process_name(pid)
                    ports_seen = set()
                    
                    for line in out.strip().split('\n'):
                        parts = line.split()
                        if len(parts) >= 5 and parts[-1] == pid:
                            # Extract port from local address (format: IP:PORT)
                            local_addr = parts[1]
                            if ':' in local_addr:
                                port = local_addr.split(':')[-1]
                                if port not in ports_seen:
                                    ports_seen.add(port)
                                    state = parts[3] if len(parts) > 3 else "UNKNOWN"
                                    process_port_map.append((pid, proc_name, port, state))
    
    else:  # Linux, Ubuntu, macOS
        # Use lsof to find ports by process name
        out = run(f"lsof -i -P -n | grep -i {process_name}")
        if out:
            for line in out.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 9:
                    command = parts[0]
                    pid = parts[1]
                    # Extract port from address (format: *:PORT or IP:PORT)
                    address = parts[8]
                    if ':' in address:
                        port = address.split(':')[-1]
                        # Filter out non-LISTEN states if needed
                        state = "LISTEN" if "LISTEN" in line else "ESTABLISHED"
                        process_port_map.append((pid, command, port, state))
    
    return process_port_map


def kill_pid(pid, silent=False):
    """Kill process by PID"""
    system = platform.system()

    if system == "Windows":
        result = run(f"taskkill /PID {pid} /F")
        return result
    else:
        result = run(f"kill -9 {pid}")
        return result if result else "Process killed successfully"


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="🔪 kport - Cross-platform port inspector and killer",
        epilog="Examples:\n"
               "  kport -i 8080                  Inspect port 8080\n"
               "  kport -im 3000 3001 3002       Inspect multiple ports\n"
               "  kport -ir 3000-3010            Inspect port range\n"
               "  kport -ip node                 Inspect all processes matching 'node'\n"
               "  kport -k 8080                  Kill process using port 8080\n"
               "  kport -ka 3000 3001 3002       Kill processes on multiple ports\n"
               "  kport -kr 3000-3010            Kill processes on port range\n"
               "  kport -kp node                 Kill all processes matching 'node'\n"
               "  kport -l                       List all listening ports\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-i", "--inspect", type=int, metavar="PORT", 
                       help="Inspect which process is using the specified port")
    parser.add_argument("-im", "--inspect-multiple", type=int, nargs="+", metavar="PORT",
                       help="Inspect multiple ports")
    parser.add_argument("-ir", "--inspect-range", type=str, metavar="RANGE",
                       help="Inspect port range (e.g., 3000-3010)")
    parser.add_argument("-ip", "--inspect-process", type=str, metavar="NAME",
                       help="Inspect all processes matching the given name")
    parser.add_argument("-k", "--kill", type=int, metavar="PORT",
                       help="Kill the process using the specified port")
    parser.add_argument("-kp", "--kill-process", type=str, metavar="NAME",
                       help="Kill all processes matching the given name")
    parser.add_argument("-ka", "--kill-all", type=int, nargs="+", metavar="PORT",
                       help="Kill processes on multiple ports")
    parser.add_argument("-kr", "--kill-range", type=str, metavar="RANGE",
                       help="Kill processes on port range (e.g., 3000-3010)")
    parser.add_argument("-l", "--list", action="store_true",
                       help="List all listening ports and their processes")
    parser.add_argument("-v", "--version", action="version", version="kport 2.1.1")

    args = parser.parse_args()

    # If no arguments provided, show help
    if not (args.inspect or args.inspect_multiple or args.inspect_range or args.inspect_process or 
            args.kill or args.list or args.kill_process or args.kill_all or args.kill_range):
        parser.print_help()
        sys.exit(0)

    if args.list:
        list_all_ports()

    if args.inspect_multiple:
        print(colorize(f"\n🔍 Inspecting {len(args.inspect_multiple)} port(s)...\n", Colors.CYAN + Colors.BOLD))
        
        results = []
        for port in args.inspect_multiple:
            validate_port(port)
            pid, info = find_pid(port)
            if pid:
                proc_name = get_process_name(pid)
                results.append((port, pid, proc_name))
        
        if not results:
            print(colorize(f"❌ No processes found on any of the specified ports", Colors.RED))
        else:
            print(colorize(f"{'Port':<10} {'PID':<10} {'Process':<30}", Colors.BOLD))
            print("─" * 60)
            
            for port, pid, proc_name in results:
                print(f"{colorize(str(port), Colors.CYAN):<19} {pid:<10} {proc_name:<30}")
            
            print(colorize(f"\n✓ Found processes on {len(results)}/{len(args.inspect_multiple)} port(s)", Colors.GREEN))

    if args.inspect_range:
        ports = parse_port_range(args.inspect_range)
        print(colorize(f"\n🔍 Inspecting port range {args.inspect_range} ({len(ports)} ports)...\n", Colors.CYAN + Colors.BOLD))
        
        results = []
        for port in ports:
            pid, info = find_pid(port)
            if pid:
                proc_name = get_process_name(pid)
                results.append((port, pid, proc_name))
        
        if not results:
            print(colorize(f"❌ No processes found in port range {args.inspect_range}", Colors.RED))
        else:
            print(colorize(f"{'Port':<10} {'PID':<10} {'Process':<30}", Colors.BOLD))
            print("─" * 60)
            
            for port, pid, proc_name in results:
                print(f"{colorize(str(port), Colors.CYAN):<19} {pid:<10} {proc_name:<30}")
            
            print(colorize(f"\n✓ Found processes on {len(results)}/{len(ports)} port(s) in range", Colors.GREEN))

    if args.inspect_process:
        print(colorize(f"\n🔍 Inspecting processes matching '{args.inspect_process}'...\n", Colors.CYAN + Colors.BOLD))
        
        process_info = find_ports_by_process_name(args.inspect_process)
        
        if not process_info:
            print(colorize(f"❌ No processes found matching '{args.inspect_process}'", Colors.RED))
        else:
            print(colorize(f"Found {len(process_info)} connection(s) for processes matching '{args.inspect_process}':\n", Colors.YELLOW))
            
            # Group by PID for better display
            pid_groups = {}
            for pid, proc_name, port, state in process_info:
                if pid not in pid_groups:
                    pid_groups[pid] = {'name': proc_name, 'ports': []}
                pid_groups[pid]['ports'].append((port, state))
            
            print(colorize(f"{'PID':<10} {'Process':<25} {'Port':<10} {'State':<15}", Colors.BOLD))
            print("─" * 70)
            
            for pid, data in pid_groups.items():
                proc_name = data['name']
                ports = data['ports']
                
                # Print first port
                if ports:
                    port, state = ports[0]
                    print(f"{colorize(pid, Colors.CYAN):<19} {proc_name:<25} {port:<10} {state:<15}")
                    
                    # Print additional ports for same PID
                    for port, state in ports[1:]:
                        print(f"{'':<10} {'':<25} {port:<10} {state:<15}")
            
            print(colorize(f"\n✓ Total processes found: {len(pid_groups)}", Colors.GREEN))
            print(colorize(f"✓ Total connections: {len(process_info)}", Colors.GREEN))

    if args.kill_process:
        print(colorize(f"\n🔪 Killing all processes matching '{args.kill_process}'...\n", Colors.CYAN + Colors.BOLD))
        
        pids = find_pids_by_process_name(args.kill_process)
        if not pids:
            print(colorize(f"❌ No processes found matching '{args.kill_process}'", Colors.RED))
        else:
            print(colorize(f"Found {len(pids)} process(es) matching '{args.kill_process}':", Colors.YELLOW))
            print("─" * 50)
            
            for pid in pids:
                proc_name = get_process_name(pid)
                print(colorize(f"  PID {pid}: {proc_name}", Colors.WHITE))
            
            # Ask for confirmation
            try:
                confirm = input(colorize(f"\nAre you sure you want to kill {len(pids)} process(es)? (y/N): ", Colors.MAGENTA))
                if confirm.lower() not in ['y', 'yes']:
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                    sys.exit(0)
            except KeyboardInterrupt:
                print(colorize("\n\nOperation cancelled.", Colors.YELLOW))
                sys.exit(0)
            
            # Kill all processes
            killed_count = 0
            for pid in pids:
                result = kill_pid(pid, silent=True)
                if result or "SUCCESS" in str(result) or "killed" in str(result).lower():
                    killed_count += 1
                    print(colorize(f"✓ Killed PID {pid}", Colors.GREEN))
                else:
                    print(colorize(f"✗ Failed to kill PID {pid}", Colors.RED))
            
            print(colorize(f"\n✓ Successfully killed {killed_count}/{len(pids)} process(es)", Colors.GREEN + Colors.BOLD))

    if args.kill_all:
        print(colorize(f"\n🔪 Killing processes on {len(args.kill_all)} port(s)...\n", Colors.CYAN + Colors.BOLD))
        
        # Validate all ports first
        for port in args.kill_all:
            validate_port(port)
        
        # Find all PIDs
        port_pid_map = {}
        for port in args.kill_all:
            pid, info = find_pid(port)
            if pid:
                port_pid_map[port] = (pid, info)
        
        if not port_pid_map:
            print(colorize(f"❌ No processes found on any of the specified ports", Colors.RED))
        else:
            print(colorize(f"Found processes on {len(port_pid_map)} port(s):", Colors.YELLOW))
            print("─" * 50)
            
            for port, (pid, info) in port_pid_map.items():
                proc_name = get_process_name(pid)
                print(colorize(f"  Port {port}: PID {pid} ({proc_name})", Colors.WHITE))
            
            # Ask for confirmation
            try:
                confirm = input(colorize(f"\nAre you sure you want to kill {len(port_pid_map)} process(es)? (y/N): ", Colors.MAGENTA))
                if confirm.lower() not in ['y', 'yes']:
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                    sys.exit(0)
            except KeyboardInterrupt:
                print(colorize("\n\nOperation cancelled.", Colors.YELLOW))
                sys.exit(0)
            
            # Kill all processes
            killed_count = 0
            for port, (pid, info) in port_pid_map.items():
                result = kill_pid(pid, silent=True)
                if result or "SUCCESS" in str(result) or "killed" in str(result).lower():
                    killed_count += 1
                    print(colorize(f"✓ Killed process on port {port} (PID {pid})", Colors.GREEN))
                else:
                    print(colorize(f"✗ Failed to kill process on port {port} (PID {pid})", Colors.RED))
            
            print(colorize(f"\n✓ Successfully killed {killed_count}/{len(port_pid_map)} process(es)", Colors.GREEN + Colors.BOLD))
            print(colorize(f"Ports freed: {', '.join(map(str, port_pid_map.keys()))}", Colors.GREEN))

    if args.kill_range:
        ports = parse_port_range(args.kill_range)
        print(colorize(f"\n🔪 Killing processes on port range {args.kill_range} ({len(ports)} ports)...\n", Colors.CYAN + Colors.BOLD))
        
        # Find all PIDs in range
        port_pid_map = {}
        for port in ports:
            pid, info = find_pid(port)
            if pid:
                port_pid_map[port] = (pid, info)
        
        if not port_pid_map:
            print(colorize(f"❌ No processes found in port range {args.kill_range}", Colors.RED))
        else:
            print(colorize(f"Found processes on {len(port_pid_map)} port(s) in range:", Colors.YELLOW))
            print("─" * 50)
            
            for port, (pid, info) in port_pid_map.items():
                proc_name = get_process_name(pid)
                print(colorize(f"  Port {port}: PID {pid} ({proc_name})", Colors.WHITE))
            
            # Ask for confirmation
            try:
                confirm = input(colorize(f"\nAre you sure you want to kill {len(port_pid_map)} process(es)? (y/N): ", Colors.MAGENTA))
                if confirm.lower() not in ['y', 'yes']:
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                    sys.exit(0)
            except KeyboardInterrupt:
                print(colorize("\n\nOperation cancelled.", Colors.YELLOW))
                sys.exit(0)
            
            # Kill all processes
            killed_count = 0
            for port, (pid, info) in port_pid_map.items():
                result = kill_pid(pid, silent=True)
                if result or "SUCCESS" in str(result) or "killed" in str(result).lower():
                    killed_count += 1
                    print(colorize(f"✓ Killed process on port {port} (PID {pid})", Colors.GREEN))
                else:
                    print(colorize(f"✗ Failed to kill process on port {port} (PID {pid})", Colors.RED))
            
            print(colorize(f"\n✓ Successfully killed {killed_count}/{len(port_pid_map)} process(es)", Colors.GREEN + Colors.BOLD))
            print(colorize(f"Ports freed: {', '.join(map(str, port_pid_map.keys()))}", Colors.GREEN))

    if args.inspect:
        validate_port(args.inspect)
        print(colorize(f"\n🔍 Inspecting port {args.inspect}...\n", Colors.CYAN + Colors.BOLD))
        
        pid, info = find_pid(args.inspect)
        if not pid:
            print(colorize(f"❌ No process found using port {args.inspect}", Colors.RED))
        else:
            print(colorize(f"✓ Port {args.inspect} is being used by PID {pid}", Colors.GREEN + Colors.BOLD))
            print(colorize("\nProcess Information:", Colors.YELLOW))
            print("─" * 50)
            print(info)

    if args.kill:
        validate_port(args.kill)
        print(colorize(f"\n🔪 Attempting to kill process on port {args.kill}...\n", Colors.CYAN + Colors.BOLD))
        
        pid, info = find_pid(args.kill)
        if not pid:
            print(colorize(f"❌ No process found using port {args.kill}", Colors.RED))
        else:
            print(colorize(f"Found PID {pid} using port {args.kill}", Colors.YELLOW))
            
            # Show process info before killing
            if info:
                print(colorize("\nProcess to be terminated:", Colors.YELLOW))
                print(info)
            
            # Ask for confirmation
            try:
                confirm = input(colorize("\nAre you sure you want to kill this process? (y/N): ", Colors.MAGENTA))
                if confirm.lower() not in ['y', 'yes']:
                    print(colorize("Operation cancelled.", Colors.YELLOW))
                    sys.exit(0)
            except KeyboardInterrupt:
                print(colorize("\n\nOperation cancelled.", Colors.YELLOW))
                sys.exit(0)
            
            result = kill_pid(pid)
            if result:
                print(colorize(f"\n✓ Successfully killed process {pid}", Colors.GREEN + Colors.BOLD))
                if "SUCCESS" in result or "killed" in result.lower():
                    print(colorize(f"Port {args.kill} is now free.", Colors.GREEN))
            else:
                print(colorize(f"\n❌ Failed to kill process {pid}", Colors.RED))
                print(colorize("You may need administrator/sudo privileges.", Colors.YELLOW))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(colorize("\n\nOperation cancelled by user.", Colors.YELLOW))
        sys.exit(0)
    except Exception as e:
        print(colorize(f"\nUnexpected error: {e}", Colors.RED))
        sys.exit(1)
