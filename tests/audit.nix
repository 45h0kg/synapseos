{ modules }:
{ hostPkgs, ... }:
{
  name = "synapse-audit";
  nodes.machine = {
    imports = modules;
    environment.systemPackages = [ hostPkgs.lynis ];
    virtualisation.memorySize = 1536;
  };
  testScript = ''
    import re
    machine.wait_for_unit("multi-user.target")
    report = machine.succeed("lynis audit system --quick --no-colors --no-log 2>&1 | tail -40")
    print(report)
    index = int(re.search(r"Hardening index : (\d+)", report).group(1))
    assert index >= 65, f"hardening index fell to {index}"
  '';
}
