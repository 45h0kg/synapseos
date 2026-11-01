{
  description = "SynapseOS: declarative, air-gapped AI red-teaming and network threat intelligence distribution";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      tools = pkgs.callPackage ./pkgs/python-tools.nix { };

      modules = [
        ./configuration.nix
        ./modules/networking/ebpf-monitors.nix
        ./modules/networking/triage.nix
        ./modules/networking/wireguard-mesh.nix
        ./modules/ai-security/airgap.nix
        ./modules/ai-security/detonation-chamber.nix
        ./modules/ai-security/garak-scanner.nix
        ./modules/ai-security/sandbox-runtime.nix
        ./modules/desktop/tui-dashboard.nix
        { _module.args.synapseTools = tools; }
      ];

      vmTest = path: pkgs.testers.runNixOSTest (import path { inherit modules; });
    in
    {
      nixosModules.default = { imports = modules; };

      nixosConfigurations.synapseOS = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = modules ++ [
          { system.configurationRevision = self.rev or self.dirtyRev or null; }
          "${nixpkgs}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
          ./modules/iso.nix
        ];
      };

      packages.${system} = {
        inherit (tools) garak inspect_ai;
        iso = self.nixosConfigurations.synapseOS.config.system.build.isoImage;
        default = self.packages.${system}.iso;
      };

      checks.${system} = {
        hardening = vmTest ./tests/hardening.nix;
        airgap = vmTest ./tests/airgap.nix;
        sandbox = vmTest ./tests/sandbox.nix;
        ebpf = vmTest ./tests/ebpf.nix;
        audit = vmTest ./tests/audit.nix;
        chamber = vmTest ./tests/chamber.nix;
        ai-tools = pkgs.runCommand "synapse-ai-tools-smoke" { nativeBuildInputs = [ tools.garak tools.inspect_ai ]; } ''
          export HOME=$TMPDIR
          garak --version
          inspect --version
          touch $out
        '';
      };
    };
}
