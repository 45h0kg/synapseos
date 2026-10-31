{ config, lib, pkgs, ... }:

let
  enforce = pkgs.writeShellApplication {
    name = "synapse-airgap-enforce";
    runtimeInputs = with pkgs; [ coreutils iproute2 nftables ];
    text = ''
      nft flush ruleset
      nft -f - <<'RULES'
      table inet airgap {
        chain input { type filter hook input priority -100; policy drop; iifname "lo" accept; }
        chain forward { type filter hook forward priority -100; policy drop; }
        chain output { type filter hook output priority -100; policy drop; oifname "lo" accept; }
      }
      RULES

      for dev in /sys/class/net/*; do
        name=$(basename "$dev")
        [ "$name" = lo ] && continue
        ip link set "$name" down || true
        if [ -e "$dev/device/driver" ]; then
          bus_id=$(basename "$(readlink -f "$dev/device")")
          echo "$bus_id" > "$dev/device/driver/unbind"
          echo "unbound $name ($bus_id)"
        fi
      done

      ip -4 route flush table main || true
      ip -6 route flush table main || true
      ip -4 rule add priority 1 prohibit
      ip -6 rule add priority 1 prohibit
    '';
  };
in
{
  options.synapseos.airgap.atBoot = lib.mkEnableOption "entering airgap.target at every boot";

  config = {
    environment.systemPackages = [ enforce ];

    systemd.services.airgap-enforce = {
      description = "Unbind physical NICs and lock routing";
      unitConfig.DefaultDependencies = false;
      before = [ "airgap.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = lib.getExe enforce;
      };
    };

    # One way by design: a reboot is the only exit.
    systemd.targets.airgap = {
      description = "SynapseOS air-gapped execution mode";
      requires = [ "airgap-enforce.service" ];
      conflicts = [
        "NetworkManager.service"
        "wpa_supplicant.service"
        "dhcpcd.service"
        "systemd-networkd.service"
        "sshd.service"
      ];
      wantedBy = lib.mkIf config.synapseos.airgap.atBoot [ "multi-user.target" ];
    };
  };
}
