{ modules }:
{ hostPkgs, ... }:
{
  name = "synapse-audit";
  nodes.machine = {
    imports = modules;
    environment.systemPackages = [ pkgs.lynis ];
    virtualisation.memorySize = 1536;
  };
  testScript = ''
    machine.wait_for_unit("multi-user.target")
    report = machine.succeed("lynis audit system --quick --no-colors --no-log 2>&1 | tail -40")
    print(report)
    assert "Hardening index" in report, report
  '';
}
