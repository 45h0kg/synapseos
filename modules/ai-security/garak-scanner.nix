{ config, lib, pkgs, synapseTools, ... }:

let
  garak = pkgs.writeShellApplication {
    name = "synapse-garak";
    text = ''
      exec synapse-sandbox --state synapse-garak -- ${synapseTools.garak}/bin/garak "$@"
    '';
  };
in
{
  options.synapseos.aiTools.enable = lib.mkEnableOption "garak and Inspect AI, which add several GB";

  config = lib.mkIf config.synapseos.aiTools.enable {
    environment.systemPackages = [
      garak
      synapseTools.garak
      synapseTools.inspect_ai
    ];
  };
}
