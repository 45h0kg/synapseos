{ modules }:
{ hostPkgs, ... }:
{
  name = "synapse-sandbox";
  nodes.machine = { imports = modules; virtualisation.memorySize = 1536; };
  testScript = ''
    machine.wait_for_unit("multi-user.target")
    devices = machine.succeed("synapse-sandbox -- ${hostPkgs.coreutils}/bin/cat /proc/net/dev")
    names = [line.split(":")[0].strip() for line in devices.splitlines() if ":" in line]
    assert names == ["lo"], devices
    uid = machine.succeed("synapse-sandbox -- ${hostPkgs.coreutils}/bin/id -u").strip()
    assert uid != "0", uid
    machine.fail("synapse-sandbox -- ${hostPkgs.coreutils}/bin/touch /etc/escaped")
    machine.fail("synapse-sandbox -- ${hostPkgs.python3}/bin/python3 -c "
                 "'import socket; socket.socket(socket.AF_INET)'")
    machine.fail("synapse-sandbox --memory 64M -- ${hostPkgs.python3}/bin/python3 -c "
                 "'b = bytearray(512 * 1024 * 1024)'")
    machine.succeed("synapse-sandbox --memory 256M -- ${hostPkgs.python3}/bin/python3 -c "
                    "'b = bytearray(64 * 1024 * 1024)'")
  '';
}
