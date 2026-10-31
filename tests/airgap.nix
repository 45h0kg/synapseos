{ modules }:
{
  name = "synapse-airgap";
  nodes.machine = { imports = modules; virtualisation.vlans = [ 1 ]; };
  nodes.peer = { networking.firewall.enable = false; virtualisation.vlans = [ 1 ]; };
  testScript = ''
    start_all()
    machine.wait_for_unit("multi-user.target")
    peer.wait_for_unit("network.target")
    machine.wait_until_succeeds("ping -c1 -W1 peer", timeout=60)

    machine.succeed("systemctl start airgap.target")
    machine.succeed("systemctl is-active airgap.target")

    for path in machine.succeed("ls -d /sys/class/net/*").split():
        if not path.endswith("/lo"):
            machine.fail(f"test -e {path}/device/driver")
    machine.fail("ip -4 route show | grep -q .")
    machine.succeed("ip rule show | grep -q prohibit")
    machine.fail("ping -c1 -W1 peer")
    machine.succeed("ping -c1 -W1 127.0.0.1")
    peer.fail("ping -c1 -W1 machine")
  '';
}
