{ config, lib, pkgs, synapseTools, ... }:

let
  garak = pkgs.writeShellApplication {
    name = "synapse-garak";
    text = ''
      exec synapse-sandbox --state synapse-garak -- ${synapseTools.garak}/bin/garak "$@"
    '';
  };

  # Inspect loads this encoding at runtime, which fails offline. tiktoken names cache files by the URL's SHA-1.
  tiktokenCache = pkgs.linkFarm "tiktoken-cache" [{
    name = "fb374d419588a4632f3f557e76b4b70aebbca790";
    path = pkgs.fetchurl {
      url = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken";
      hash = "sha256-RGqVOMtsNI41FhINfAiwn1fDZJXirP/+WaW/iwz7Gi0=";
    };
  }];
in
{
  options.synapseos.aiTools.enable = lib.mkEnableOption "garak and Inspect AI, which add several GB";

  config = lib.mkIf config.synapseos.aiTools.enable {
    environment.systemPackages = [
      garak
      synapseTools.garak
      synapseTools.inspect_ai
    ];
    environment.variables.TIKTOKEN_CACHE_DIR = "${tiktokenCache}";
  };
}
