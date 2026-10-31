{ config, lib, pkgs, ... }:

let
  dashboard = pkgs.writeScriptBin "synapse-dashboard" (
    "#!${pkgs.python3}/bin/python3\n" + builtins.readFile ./dashboard.py
  );

  hyprlandConfig = pkgs.writeText "hyprland.conf" ''
    exec-once = ${pkgs.foot}/bin/foot ${dashboard}/bin/synapse-dashboard
    $mod = SUPER
    bind = $mod, Return, exec, ${pkgs.foot}/bin/foot
    bind = $mod, Q, killactive
    bind = $mod SHIFT, E, exit
  '';
in
{
  options.synapseos.dashboard.enable = lib.mkEnableOption "the boot dashboard and Hyprland session";

  config = {
    environment.systemPackages = [ dashboard ];

    programs.hyprland.enable = lib.mkIf config.synapseos.dashboard.enable true;

    # The dashboard takes over tty1 at login. Run Hyprland from the shell after.
    environment.loginShellInit = lib.mkIf config.synapseos.dashboard.enable ''
      if [ "$(tty)" = /dev/tty1 ]; then
        ${dashboard}/bin/synapse-dashboard
      fi
    '';

    systemd.tmpfiles.rules = lib.mkIf config.synapseos.dashboard.enable [
      "d /home/synapse/.config 0755 synapse users -"
      "d /home/synapse/.config/hypr 0755 synapse users -"
      "L+ /home/synapse/.config/hypr/hyprland.conf - - - - ${hyprlandConfig}"
    ];
  };
}
