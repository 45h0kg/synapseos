{ config, lib, ... }:

let
  cfg = config.synapseos.wireguardMesh;
in
{
  options.synapseos.wireguardMesh = {
    enable = lib.mkEnableOption "the WireGuard telemetry mesh";

    address = lib.mkOption {
      type = lib.types.str;
      example = "10.73.0.1/24";
      description = "This node's address on the mesh.";
    };

    listenPort = lib.mkOption {
      type = lib.types.port;
      default = 51820;
      description = "UDP port WireGuard listens on.";
    };

    privateKeyFile = lib.mkOption {
      type = lib.types.path;
      example = "/run/keys/wg-synapse";
      description = "Runtime path of the private key. It must stay out of the Nix store.";
    };

    peers = lib.mkOption {
      type = lib.types.listOf lib.types.attrs;
      default = [ ];
      description = "WireGuard peers, in the format of networking.wireguard.interfaces.<name>.peers.";
    };
  };

  config = lib.mkIf cfg.enable {
    networking.firewall.allowedUDPPorts = [ cfg.listenPort ];

    networking.wireguard.interfaces.wg-synapse = {
      ips = [ cfg.address ];
      inherit (cfg) listenPort privateKeyFile peers;
    };
  };
}
