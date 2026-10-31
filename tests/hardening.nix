{ modules }:
{
  name = "synapse-hardening";
  nodes.machine = { imports = modules; };
  testScript = ''
    machine.wait_for_unit("multi-user.target")
    cmdline = machine.succeed("cat /proc/cmdline")
    for param in ["init_on_alloc=1", "init_on_free=1", "vsyscall=none"]:
        assert param in cmdline, param
    assert machine.succeed("sysctl -n kernel.kptr_restrict").strip() == "2"
    assert machine.succeed("sysctl -n user.max_user_namespaces").strip() == "0"
    machine.fail("su synapse -s /bin/sh -c 'unshare -U true'")
    machine.succeed("nft list ruleset")
    machine.succeed("synapse-dashboard --once | grep -q 'air gap'")
    machine.succeed("command -v tshark nmap tcpdump synapse-triage")
  '';
}
