{ pkgs, lib, ... }:

{
  # linux-hardened was removed from nixpkgs in March 2026 for lack of
  # maintenance, so this is the 6.18 LTS kernel hardened at boot and by sysctl.
  boot.kernelPackages = pkgs.linuxPackages_6_18;

  boot.kernelParams = [
    "init_on_alloc=1"
    "init_on_free=1"
    "page_alloc.shuffle=1"
    "slab_nomerge"
    "randomize_kstack_offset=on"
    "vsyscall=none"
    "pti=on"
    "oops=panic"
  ];

  boot.blacklistedKernelModules = [
    "dccp"
    "sctp"
    "rds"
    "tipc"
    "firewire-core"
    "thunderbolt"
  ];

  boot.kernel.sysctl = {
    "kernel.dmesg_restrict" = 1;
    "kernel.kptr_restrict" = 2;
    "kernel.yama.ptrace_scope" = 2;
    "kernel.kexec_load_disabled" = 1;
    "kernel.perf_event_paranoid" = 3;
    "kernel.unprivileged_bpf_disabled" = 1;
    "net.core.bpf_jit_harden" = 2;
    "dev.tty.ldisc_autoload" = 0;
    "vm.unprivileged_userfaultfd" = 0;
    "fs.protected_fifos" = 2;
    "fs.protected_regular" = 2;
    "fs.suid_dumpable" = 0;

    "net.ipv4.ip_forward" = 0;
    "net.ipv6.conf.all.forwarding" = 0;
    "net.ipv4.tcp_syncookies" = 1;
    "net.ipv4.tcp_rfc1337" = 1;
    "net.ipv4.conf.all.rp_filter" = 1;
    "net.ipv4.conf.default.rp_filter" = 1;
    "net.ipv4.conf.all.accept_redirects" = 0;
    "net.ipv4.conf.default.accept_redirects" = 0;
    "net.ipv4.conf.all.send_redirects" = 0;
    "net.ipv4.conf.default.send_redirects" = 0;
    "net.ipv4.conf.all.accept_source_route" = 0;
    "net.ipv4.conf.default.accept_source_route" = 0;
    "net.ipv4.conf.all.log_martians" = 1;
    "net.ipv6.conf.all.accept_redirects" = 0;
    "net.ipv6.conf.default.accept_redirects" = 0;
    "net.ipv6.conf.all.accept_source_route" = 0;
    "net.ipv6.conf.default.accept_source_route" = 0;
  };

  # Disables user namespaces system-wide. Root-owned systemd sandboxes still
  # work. The Nix build sandbox does not, so packages are built in CI.
  security.allowUserNamespaces = false;
  nix.settings.sandbox = false;

  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];

  networking.hostName = "synapseos";
  networking.nftables.enable = true;
  networking.firewall.enable = true;

  users.users.synapse = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
  };

  environment.systemPackages = with pkgs; [
    git
    jq
    vim
  ];

  system.stateVersion = "26.05";
}
