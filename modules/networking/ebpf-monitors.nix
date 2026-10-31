{ config, lib, pkgs, ... }:

let
  cfg = config.synapseos.ebpfMonitor;
  portMatch = lib.concatMapStringsSep " || " (p: "args.dport == ${toString p}") cfg.ports;

  script = pkgs.writeText "synapse-monitor.bt" ''
    BEGIN { printf("synapse-ebpf: monitor attached\n"); }

    tracepoint:sock:inet_sock_set_state
    /args.newstate == 1 && (${portMatch})/
    {
      printf("synapse-ebpf: connect pid=%d comm=%s dport=%d\n", pid, comm, args.dport);
    }

    kprobe:unix_stream_sendmsg { @unix_ipc_bytes[comm] = sum(arg2); }
    kprobe:tcp_sendmsg { @tcp_tx_bytes[comm] = sum(arg2); }

    interval:s:${toString cfg.reportSeconds}
    {
      print(@unix_ipc_bytes);
      print(@tcp_tx_bytes);
      clear(@unix_ipc_bytes);
      clear(@tcp_tx_bytes);
    }
  '';
in
{
  options.synapseos.ebpfMonitor = {
    enable = lib.mkEnableOption "eBPF monitoring of AI runtime traffic" // { default = true; };

    ports = lib.mkOption {
      type = lib.types.nonEmptyListOf lib.types.port;
      default = [ 8000 8080 11434 ];
      description = "TCP ports of local AI services whose new connections are logged.";
    };

    reportSeconds = lib.mkOption {
      type = lib.types.ints.positive;
      default = 30;
      description = "How often per-process IPC and TCP byte counts go to the journal.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ pkgs.bpftrace ];

    systemd.services.synapse-ebpf-monitor = {
      description = "SynapseOS eBPF AI traffic monitor";
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.bpftrace}/bin/bpftrace -B line ${script}";
        Restart = "on-failure";
        RestartSec = 5;
        NoNewPrivileges = true;
        ProtectHome = true;
      };
    };
  };
}
