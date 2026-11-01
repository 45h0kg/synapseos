# Boots the live ISO itself, with only the test backdoor added.
{ nixpkgs, pkgs, modules }:
let
  iso = (nixpkgs.lib.nixosSystem {
    system = "x86_64-linux";
    modules = modules ++ [
      "${nixpkgs}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
      "${nixpkgs}/nixos/modules/testing/test-instrumentation.nix"
      ../modules/iso.nix
    ];
  }).config.system.build.isoImage;

  qemuCommon = import "${nixpkgs}/nixos/lib/qemu-common.nix" { inherit (pkgs) lib stdenv; };
  qemu = qemuCommon.qemuBinary pkgs.qemu_test;
in
pkgs.testers.runNixOSTest {
  name = "synapse-iso-boot";
  nodes = { };
  testScript = ''
    import time

    start = time.time()
    machine = create_machine("${qemu} -m 6144 -smp 4 -cdrom ${iso}/iso/synapseos.iso -boot d")
    machine.start()
    machine.wait_for_unit("multi-user.target", timeout=900)
    print(f"BENCH-ISO boot_seconds={time.time() - start:.1f}")
    print("BENCH-ISO", machine.succeed("synapse-dashboard --once"))
    print("BENCH-ISO", machine.succeed("uname -r; garak --version 2>&1 | tail -1; inspect --version 2>&1 | tail -1"))
    print("BENCH-ISO", machine.succeed("df -h / /nix/store 2>&1; free -m | head -2"))
    machine.succeed("printf '\\200\\002}q\\000.' > /tmp/c.pkl")
    print("BENCH-ISO", machine.succeed("synapse-detonate scan /tmp/c.pkl --runtime pickle --timeout 120 2>&1"))
    machine.succeed("systemctl start airgap.target")
    print("BENCH-ISO", machine.succeed("systemctl is-active airgap.target; ip route | wc -l"))
    machine.shutdown()
  '';
}
