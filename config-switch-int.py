#!/usr/bin/env python3
import sys
import os
import argparse
import re

def get_interface_mac(interface_name):
    """Get MAC address of the specified interface from /sys/class/net"""
    try:
        with open(f"/sys/class/net/{interface_name}/address", 'r') as f:
            mac_address = f.read().strip()
            # Validate MAC address format
            if re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac_address.lower()):
                return mac_address
            else:
                return None
    except (FileNotFoundError, PermissionError):
        return None

def load_existing_config(interface_name, output_dir="/etc/systemd/network"):
    """Load existing configuration to use as defaults"""
    config = {
        'interface_name': interface_name,
        'mac_address': None,
        'bridge': None,
        'pvid': None,
        'egress_vlan': None,
        'vlans': [],
        'link_alias': None
    }
    
    # First try to get MAC address from system interface
    config['mac_address'] = get_interface_mac(interface_name)
    
    # Check for existing .link file
    link_file = os.path.join(output_dir, f"00-{interface_name}.link")
    if os.path.exists(link_file):
        try:
            with open(link_file, 'r') as f:
                content = f.read()
                # Parse [Match] section for MAC address
                match_section = re.search(r'\[Match\](.*?)(?=\[|$)', content, re.DOTALL)
                if match_section:
                    match_content = match_section.group(1)
                    mac_match = re.search(r'MACAddress=(.*)', match_content)
                    if mac_match:
                        config['mac_address'] = mac_match.group(1).strip()
                
                # Parse [Link] section for alias
                link_section = re.search(r'\[Link\](.*?)(?=\[|$)', content, re.DOTALL)
                if link_section:
                    link_content = link_section.group(1)
                    alias_match = re.search(r'Alias=(.*)', link_content)
                    if alias_match:
                        config['link_alias'] = alias_match.group(1).strip()
        except Exception:
            pass
    
    # Check for existing .network file
    network_file = os.path.join(output_dir, f"20-{interface_name}.network")
    if os.path.exists(network_file):
        try:
            with open(network_file, 'r') as f:
                content = f.read()
                
                # Parse [Network] section for bridge
                network_section = re.search(r'\[Network\](.*?)(?=\[|$)', content, re.DOTALL)
                if network_section:
                    network_content = network_section.group(1)
                    bridge_match = re.search(r'Bridge=(.*)', network_content)
                    if bridge_match:
                        config['bridge'] = bridge_match.group(1).strip()
                
                # Parse [VLAN] and/or [BridgeVLAN] sections for PVID and VLANs
                vlan_section = re.search(r'\[VLAN\](.*?)(?=\[|$)', content, re.DOTALL)
                if vlan_section:
                    vlan_content = vlan_section.group(1)
                    # Look for PVID in VLAN section
                    pvid_match = re.search(r'PVID\s*=\s*(\d+)', vlan_content, re.IGNORECASE)
                    if pvid_match:
                        config['pvid'] = pvid_match.group(1)
                
                bridge_vlan_section = re.search(r'\[BridgeVLAN\](.*?)(?=\[|$)', content, re.DOTALL)
                if bridge_vlan_section:
                    bridge_vlan_content = bridge_vlan_section.group(1)
                    # Look for VLAN entries
                    vlan_entries = re.findall(r'VLAN\s*=\s*(\d+)', bridge_vlan_content, re.IGNORECASE)
                    config['vlans'] = vlan_entries
                
                # Also check for VLAN entries in [Bridge] section if it exists
                bridge_section = re.search(r'\[Bridge\](.*?)(?=\[|$)', content, re.DOTALL)
                if bridge_section:
                    bridge_content = bridge_section.group(1)
                    # Look for VLAN entries
                    vlan_entries = re.findall(r'VLAN\s*=\s*(\d+)', bridge_content, re.IGNORECASE)
                    config['vlans'] = list(set(config['vlans'] + vlan_entries))
                
                # Parse [BridgeVLAN] section more specifically
                if '[BridgeVLAN]' in content:
                    bridge_vlan_match = re.search(r'\[BridgeVLAN\](.*?)(?=\[|$)', content, re.DOTALL)
                    if bridge_vlan_match:
                        bridge_vlan_content = bridge_vlan_match.group(1)
                        # Look for VLAN entries
                        vlan_entries = re.findall(r'VLAN\s*=\s*(\d+)', bridge_vlan_content, re.IGNORECASE)
                        config['vlans'] = list(set(config['vlans'] + vlan_entries))
                
                # Parse for PVID
                pvid_match = re.search(r'PVID\s*=\s*(\d+)', content, re.IGNORECASE)
                if pvid_match:
                    config['pvid'] = pvid_match.group(1)

                # Parse for EgressUntagged
                egress_match = re.search(r'EgressUntagged\s*=\s*(\d+)', content, re.IGNORECASE)
                if egress_match:
                    config['egress_vlan'] = egress_match.group(1)
                    
        except Exception as e:
            pass
    
    return config

def generate_link_content(interface_name, mac_address, link_alias):
    """Generate link file content"""
    content = f"[Match]\nName={interface_name}\n"
    
    if mac_address:
        content += f"MACAddress={mac_address}\n"
    
    content += "\n[Link]\n"
    
    if link_alias:
        content += f"Alias={link_alias}\n"
    
    return content

def generate_network_content(interface_name, bridge, pvid, egress_vlan, vlans):
    """Generate network file content"""
    content = f"[Match]\nName={interface_name}\n\n[Network]\n"
    
    if bridge:
        content += f"Bridge={bridge}\n"
    
    content += "\n[BridgeVLAN]\n"
    
    # Add all VLANs
    for vlan in vlans:
        content += f"VLAN={vlan}\n"
    
    # Add PVID if specified
    if pvid and pvid.lower() != 'none':
        content += f"PVID={pvid}\n"
    
    # Add EgressUntagged VLAN if specified
    if egress_vlan and egress_vlan.lower() !=	'none':
        content += f"EgressUntagged={egress_vlan}\n"
    
    return content

def generate_iproute2_commands(interface_name, bridge, pvid, egress_vlan, vlans):
    """Generate equivalent iproute2 commands"""
    commands = []
    
    # Add VLANs to the interface using bridge vlan commands
    # We'll add each VLAN as a tagged VLAN first
    for vlan in vlans:
        if vlan != pvid:  # Skip PVID as it's handled separately
            commands.append(f"bridge vlan add vid {vlan} dev {interface_name}")
    
    # Add PVID if specified
    if pvid:
        commands.append(f"bridge vlan add vid {pvid} dev {interface_name} pvid untagged")
    
    # Add EgressUntagged VLAN if specified
    if egress_vlan and egress_vlan != pvid:
        commands.append(f"bridge vlan add vid {egress_vlan} dev {interface_name}")
    
    return commands

def print_iproute2_commands(commands):
    """Print iproute2 commands"""
    if commands:
        print("\niproute2 commands to apply the VLAN configuration (WARNING: not tested, may not be complete):")
        print("-" * 50)
        for cmd in commands:
            print(cmd)
        print("-" * 50)
        print("Run these commands with 'sudo' to apply immediately")
    else:
        print("\nNo iproute2 commands needed (no VLAN configuration)")

def print_systemd_commands():
    """Print systemd commands to apply configuration"""
    print("\nTo apply systemd network configuration:")
    print("-" * 40)
    print("sudo systemctl daemon-reload")
    print("sudo systemctl restart systemd-networkd")
    print("-" * 40)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate systemd network configuration and iproute2 commands')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode')
    parser.add_argument('--interface', help='Interface name')
    parser.add_argument('--mac', help='MAC address')
    parser.add_argument('--alias', help='Interface alias')
    parser.add_argument('--bridge', help='Bridge name')
    parser.add_argument('--pvid', help='Primary VLAN ID')
    parser.add_argument('--egress', help='Egress VLAN ID')
    parser.add_argument('--vlans', help='Comma-separated VLAN IDs')
    
    args = parser.parse_args()
    
    # Handle interactive mode
    if args.interactive or (not args.interface and not args.mac and not args.alias and not args.bridge and not args.pvid and not args.egress and not args.vlans):
        print("Interactive mode:")
        print("=" * 50)
        
        # Get interface name
        interface_name = input("Interface name: ").strip()
        if not interface_name:
            print("Error: Interface name is required")
            return
        
        # Load existing configuration
        config = load_existing_config(interface_name)
        config['interface_name'] = interface_name
        
        # Get user input for all parameters
        print("\nCurrent configuration values (press Enter to keep current or use new value):")
        print(f"Interface: {config['interface_name']}")
        config['mac_address'] = input(f"MAC address [{config['mac_address'] or 'none'}]: ").strip() or config['mac_address']
        config['link_alias'] = input(f"Alias [{config['link_alias'] or 'none'}]: ").strip() or config['link_alias']
        config['bridge'] = input(f"Bridge [{config['bridge'] or 'none'}]: ").strip() or config['bridge']
        config['pvid'] = input(f"PVID [{config['pvid'] or 'none'}]: ").strip() or config['pvid']
        config['egress_vlan'] = input(f"Egress Untagged [{config['egress_vlan'] or 'none'}]: ").strip() or config['egress_vlan']
        vlans_input = input(f"VLAN IDs (comma-separated) [{','.join(config['vlans']) or 'none'}]: ").strip()
        config['vlans'] = vlans_input.split(',') if vlans_input else config['vlans']
        
    else:
        # Command-line mode
        config = {
            'interface_name': args.interface,
            'mac_address': args.mac,
            'link_alias': args.alias,
            'bridge': args.bridge,
            'pvid': args.pvid,
            'egress_vlan': args.egress,
            'vlans': args.vlans.split(',') if args.vlans else []
        }
    
    # Validate required fields
    if not config['interface_name']:
        print("Error: Interface name is required")
        return
    
    # Generate configuration files
    print("\nGenerated configuration:")
    print("=" * 50)
    
    link_content = generate_link_content(
        config['interface_name'], 
        config['mac_address'], 
        config['link_alias']
    )
    
    network_content = generate_network_content(
        config['interface_name'],
        config['bridge'],
        config['pvid'],
        config['egress_vlan'],
        config['vlans']
    )
    
    print("Link file content:")
    print(link_content)
    print("Network file content:")
    print(network_content)
    
    # Generate iproute2 commands
    iproute2_commands = generate_iproute2_commands(
        config['interface_name'],
        config['bridge'],
        config['pvid'],
        config['egress_vlan'],
        config['vlans']
    )
    
    print_iproute2_commands(iproute2_commands)
    
    # Print systemd commands
    print_systemd_commands()
    
    # Ask for confirmation before writing
    confirm = input("\nWrite these files to /etc/systemd/network/? (y/N): ").strip().lower()
    if confirm == 'y':
        try:
            # Create directory if it doesn't exist
            os.makedirs("/etc/systemd/network", exist_ok=True)
            
            # Write .link file
            link_filename = f"/etc/systemd/network/00-{config['interface_name']}.link"
            with open(link_filename, 'w') as f:
                f.write(link_content)
            
            # Write .network file
            network_filename = f"/etc/systemd/network/20-{config['interface_name']}.network"
            with open(network_filename, 'w') as f:
                f.write(network_content)
            
            print(f"\nFiles written successfully:")
            print(f"  {link_filename}")
            print(f"  {network_filename}")
            
        except Exception as e:
            print(f"Error writing files: {e}")
    else:
        print("Files not written.")

if __name__ == "__main__":
    main()
