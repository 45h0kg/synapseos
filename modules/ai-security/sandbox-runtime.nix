{ config, lib, pkgs, ... }:

let
  cfg = config.synapseos;

  models = pkgs.linkFarm "synapse-models" (
    lib.mapAttrsToList (name: model: {
      inherit name;
      path = pkgs.fetchurl { inherit (model) url hash; };
    }) cfg.models
  );

  sandbox = pkgs.writeShellApplication {
    name = "synapse-sandbox";
    runtimeInputs = [ pkgs.systemd pkgs.coreutils ];
    text = ''
      if [ "$(id -u)" -ne 0 ]; then
        exec sudo "$0" "$@"
      fi

      memory=${cfg.sandbox.memoryMax}
      cpu=${cfg.sandbox.cpuQuota}
      state=()
      while [ "$#" -gt 0 ]; do
        case "$1" in
          --memory) memory=$2; shift 2 ;;
          --cpu) cpu=$2; shift 2 ;;
          --state)
            state=(-p "StateDirectory=$2" -p "Environment=HOME=/var/lib/$2")
            shift 2
            ;;
          --) shift; break ;;
          *) break ;;
        esac
      done
      if [ "$#" -eq 0 ]; then
        echo "usage: synapse-sandbox [--memory 8G] [--cpu 400%] [--state NAME] -- COMMAND" >&2
        exit 2
      fi
      exec systemd-run --quiet --collect --wait --pipe \
        -p DynamicUser=yes \
        -p PrivateNetwork=yes \
        -p RestrictAddressFamilies=AF_UNIX \
        -p IPAddressDeny=any \
        -p MemoryMax="$memory" \
        -p MemorySwapMax=0 \
        -p CPUQuota="$cpu" \
        -p ProtectSystem=strict \
        -p ProtectHome=yes \
        -p PrivateTmp=yes \
        -p PrivateDevices=yes \
        -p ProtectKernelTunables=yes \
        -p ProtectKernelModules=yes \
        -p ProtectKernelLogs=yes \
        -p ProtectControlGroups=yes \
        -p ProtectProc=invisible \
        -p NoNewPrivileges=yes \
        -p CapabilityBoundingSet= \
        -p SystemCallArchitectures=native \
        -p SystemCallFilter=@system-service \
        "''${state[@]}" \
        "$@"
    '';
  };
in
{
  options.synapseos = {
    sandbox = {
      memoryMax = lib.mkOption {
        type = lib.types.str;
        default = "8G";
        description = "Default hard memory limit for a sandboxed runtime.";
      };

      cpuQuota = lib.mkOption {
        type = lib.types.str;
        default = "400%";
        description = "Default CPU quota for a sandboxed runtime.";
      };
    };

    models = lib.mkOption {
      type = lib.types.attrsOf (
        lib.types.submodule {
          options = {
            url = lib.mkOption { type = lib.types.str; };
            hash = lib.mkOption { type = lib.types.str; };
          };
        }
      );
      default = { };
      example = lib.literalExpression ''
        { "model.gguf" = { url = "https://example.org/model.gguf"; hash = "sha256-..."; }; }
      '';
      description = "Model files baked into the image, pinned by hash, under /etc/synapseos/models.";
    };
  };

  config = {
    environment.systemPackages = [
      sandbox
      pkgs.llama-cpp
    ];

    environment.etc."synapseos/models".source = models;
  };
}
