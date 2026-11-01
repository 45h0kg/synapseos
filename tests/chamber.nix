{ modules }:
{ hostPkgs, ... }:
{
  name = "synapse-chamber";
  nodes.machine = {
    imports = modules;
    synapseos.chamber.torch = true;
    virtualisation.memorySize = 4096;
    virtualisation.diskSize = 8192;
    boot.kernel.sysctl."vm.panic_on_oom" = 0;
  };
  testScript = ''
    import json


    def scan(name, runtime):
        status, out = machine.execute(f"synapse-detonate scan /tmp/fx/{name} --runtime {runtime} 2>&1")
        print(out)
        path = [l.split()[1] for l in out.splitlines() if l.startswith("receipt:")]
        assert path, out
        return status, json.loads(machine.succeed(f"cat {path[0]}")), path[0]


    def kinds(receipt):
        return {f["kind"] for f in receipt["findings"]}


    machine.wait_for_unit("multi-user.target")
    CG = "/sys/fs/cgroup/system.slice/sshd.service"
    machine.succeed("mkdir -p /sys/fs/cgroup/diag")
    CASES = {
      "plain-int": 'tracepoint:syscalls:sys_enter_socket { printf("%d\\n", args.family); }',
      "plain-str": 'tracepoint:syscalls:sys_enter_openat { printf("%s\\n", str(args.filename)); }',
      "no-args": 'tracepoint:syscalls:sys_enter_socket { printf("x\\n"); }',
      "cgroup-noargs": 'tracepoint:syscalls:sys_enter_socket /cgroup == cgroupid("/sys/fs/cgroup/diag")/ { printf("x\\n"); }',
      "cgroup-int": 'tracepoint:syscalls:sys_enter_socket /cgroup == cgroupid("/sys/fs/cgroup/diag")/ { printf("%d\\n", args.family); }',
      "strlen-int": 'config = { max_strlen = 256 }\ntracepoint:syscalls:sys_enter_socket { printf("%d\\n", args.family); }',
      "strlen-str": 'config = { max_strlen = 256 }\ntracepoint:syscalls:sys_enter_openat { printf("%s\\n", str(args.filename)); }',
      "maskedtype": 'tracepoint:syscalls:sys_enter_socket { printf("%d\\n", args.type & 15); }',
      "pidmap": 'BEGIN { @t[1]=1; } tracepoint:syscalls:sys_enter_socket /@t[tid]/ { printf("%d\\n", args.family); }',
      "fork": 'tracepoint:sched:sched_process_fork { printf("%d\\n", args.child_pid); }',
      "rawsys": 'tracepoint:raw_syscalls:sys_enter /cgroup == cgroupid("/sys/fs/cgroup/diag")/ { printf("%d %d\\n", args.id, args.args[0]); }',
    }
    for label, program in CASES.items():
        machine.succeed(f"cat > /tmp/d.bt <<'EOF'\n{program}\nEOF")
        rc, text = machine.execute("timeout -s INT 6 bpftrace -v -B line /tmp/d.bt 2>&1 | tail -4; echo rc=${PIPESTATUS[0]}")
        print("DIAG", label, text.replace(chr(10), " | ")[-260:])
    machine.succeed("cat /sys/kernel/tracing/events/syscalls/sys_enter_socket/format | tail -12 | sed 's/^/DIAGFMT /' >&2")
    print("DIAG sysctl", machine.succeed("sysctl kernel.unprivileged_bpf_disabled kernel.perf_event_paranoid net.core.bpf_jit_harden; cat /sys/kernel/security/lsm; uname -r"))
    print("DIAG mon", machine.succeed("bpftrace --version; systemctl is-active synapse-ebpf-monitor"))
    machine.succeed("mkdir -p /tmp/fx && ${hostPkgs.python3}/bin/python3 ${./chamber-fixtures.py} /tmp/fx")

    with subtest("inert files show no divergence"):
        for name, runtime in [("clean.pkl", "pickle"), ("clean.gguf", "jinja"), ("clean.pt", "torch")]:
            status, receipt, _ = scan(name, runtime)
            assert status == 0 and receipt["verdict"] == "no-divergence", receipt

    with subtest("a shell payload diverges, whatever the format"):
        for name, runtime in [("rce.pkl", "pickle"), ("ssti.gguf", "jinja"), ("rce.pt", "torch")]:
            status, receipt, _ = scan(name, runtime)
            assert status == 10 and "exec" in kinds(receipt), receipt

    with subtest("a gated stealer is proven to exfiltrate over TCP and DNS"):
        status, receipt, path = scan("stealer.pkl", "pickle")
        assert status == 20, receipt
        assert {"honey-read", "tcp", "dns", "exfiltration"} <= kinds(receipt), receipt
        secret = machine.succeed(f"cat {path}")
        assert "AKIA" not in secret, "a honeytoken reached the receipt"

    with subtest("the behaviour digest repeats"):
        first = scan("rce.pkl", "pickle")[1]["behaviour_digest"]
        second = scan("rce.pkl", "pickle")[1]["behaviour_digest"]
        assert first == second, (first, second)

    with subtest("receipts verify and tampering is detected"):
        _, receipt, path = scan("rce.pkl", "pickle")
        assert "/nix/store/" in receipt["lab"]["system"], receipt
        machine.succeed(f"synapse-detonate verify {path} | grep -q 'signature: valid'")
        machine.succeed(f"sed -i 's/\"verdict\": \"divergent\"/\"verdict\": \"no-divergence\"/' {path}")
        machine.fail(f"synapse-detonate verify {path}")

    with subtest("the chamber leaves no namespaces behind"):
        assert machine.succeed("ip netns list").strip() == ""
  '';
}
