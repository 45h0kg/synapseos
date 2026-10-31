{ pkgs, ... }:

let
  triage = pkgs.writeShellApplication {
    name = "synapse-triage";
    runtimeInputs = [ pkgs.wireshark-cli ];
    text = ''
      if [ "$#" -ne 2 ]; then
        echo "usage: synapse-triage <interface> <cisco|l2|routing|ha|ai>" >&2
        exit 2
      fi
      case "$2" in
        cisco)   filter='cdp || vtp || dtp || eigrp || hsrp' ;;
        l2)      filter='lldp || cdp || stp || vlan || lacp' ;;
        routing) filter='ospf || eigrp || bgp || isis' ;;
        ha)      filter='hsrp || vrrp || glbp' ;;
        ai)      filter='tcp.port in {8000 8080 11434}' ;;
        *)       echo "unknown profile: $2" >&2; exit 2 ;;
      esac
      exec tshark -i "$1" -Y "$filter"
    '';
  };
in
{
  programs.wireshark = {
    enable = true;
    package = pkgs.wireshark-cli;
  };

  users.users.synapse.extraGroups = [ "wireshark" ];

  environment.systemPackages = [
    triage
    pkgs.nmap
    pkgs.tcpdump
    pkgs.wireshark-cli
  ];
}
