{ config, lib, pkgs, ... }:

let
  cfg = config.synapseos.chamber;

  python = pkgs.python3.withPackages (
    ps: [ ps.jinja2 ] ++ lib.optional cfg.torch ps.torch
  );

  detonate = pkgs.writeShellApplication {
    name = "synapse-detonate";
    runtimeInputs = with pkgs; [
      bpftrace
      iproute2
      nftables
      openssl
      systemd
    ];
    text = ''
      if [ "$(id -u)" -ne 0 ]; then
        exec sudo "$0" "$@"
      fi
      exec ${python}/bin/python3 ${./detonate.py} "$@"
    '';
  };
in
{
  options.synapseos.chamber = {
    enable = lib.mkEnableOption "the model detonation chamber" // { default = true; };
    torch = lib.mkEnableOption "the torch.load runtime, which adds several GB";
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ detonate ];
    systemd.tmpfiles.rules = [ "d /var/lib/synapse-chamber 0755 root root -" ];
  };
}
