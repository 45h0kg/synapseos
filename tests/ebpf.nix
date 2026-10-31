{ modules }:
{ hostPkgs, ... }:
{
  name = "synapse-ebpf";
  nodes.machine = { imports = modules; virtualisation.memorySize = 2048; };
  testScript = ''
    machine.wait_for_unit("synapse-ebpf-monitor.service")
    machine.wait_until_succeeds(
        "journalctl -u synapse-ebpf-monitor | grep -q 'monitor attached'", timeout=120)
    machine.succeed("${hostPkgs.python3}/bin/python3 -m http.server 8000 >/dev/null 2>&1 &")
    machine.wait_for_open_port(8000)
    machine.succeed("curl -s -o /dev/null http://127.0.0.1:8000/")
    machine.wait_until_succeeds(
        "journalctl -u synapse-ebpf-monitor | grep -q 'connect .* dport=8000'", timeout=60)
  '';
}
