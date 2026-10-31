# SynapseOS: Declarative, Air-Gapped AI Red-Teaming & Network Threat Intelligence Distribution

SynapseOS is a highly customized, **immutable, reproducible Linux operating system** engineered specifically for AI model vulnerability exploitation, prompt injection evaluation, and high-throughput network threat intelligence parsing. Designed as a GitOps-driven meta-distribution, the entire system architecture is defined as pure code and compiled directly via automated infrastructure pipelines.

---

## 🏗️ System Architecture & Core Pillars

```
+-----------------------------------------------------------------------+
|                             SynapseOS                                 |
+-----------------------------------------------------------------------+
|  [AI Security Tooling]      [Enterprise Networking]     [GitOps Core] |
|  - Garak / Inspect AI       - eBPF Kernel Hooks         - NixOS Flake |
|  - Local Sandboxed SLMs     - WireGuard / Tshark        - GitHub CI   |
+-----------------------------------------------------------------------+
|                      [Hardened Air-Gapped Shell]                      |
+-----------------------------------------------------------------------+
```

### 1. Immutable & Hardened Core
* **Declarative Base:** Built on top of NixOS Flakes, achieving 100% cryptographic reproducibility. A single git commit represents the entire state of the operating system.
* **Kernel Hardening:** Runs a customized `linux-hardened` kernel compiled with advanced runtime protections, strict memory zeroing, and disabled unprivileged user namespaces.

### 2. AI Red-Teaming & SecOps Sandbox
* **Automated LLM Fuzzing:** Pre-baked and containerized instances of `garak` (LLM Vulnerability Scanner) and `Inspect AI` for immediate validation of target models against prompt injection, data poisoning, and model inversion.
* **Air-Gapped Execution Mode:** A custom systemd target (`airgap.target`) that immediately unbinds physical network interfaces, locks routing tables, and runs local, untrusted model weights inside isolated, memory-constrained runtimes.

### 3. Enterprise-Grade Network Telemetry
* **eBPF-Powered Inspection:** Kernel-level telemetry via eBPF hooks monitoring system calls and data streams vectoring into local AI clusters.
* **Network Triage Toolkit:** Pre-configured `Tshark`, `Tcpdump`, and `Nmap` environments optimized with custom profiles for parsing protocol layers down to Cisco enterprise network interface baselines.

---

## 📂 Repository Structure

```text
.
├── .github/
│   └── workflows/
│       └── build-hardened-iso.yml   # CI pipeline compiling the secure ISO artifact
├── modules/
│   ├── networking/
│   │   ├── ebpf-monitors.nix        # Kernel eBPF hooks for monitoring AI traffic
│   │   └── wireguard-mesh.nix       # Declarative, secure peer-to-peer telemetry
│   ├── ai-security/
│   │   ├── garak-scanner.nix        # Packaged prompt injection & fuzzing engine
│   │   └── sandbox-runtime.nix      # Isolated runtimes for running untrusted weights
│   └── desktop/
│       └── tui-dashboard.nix        # Minimal Wayland/Hyprland environment & custom TUI
├── flake.nix                        # Main system entry point & lockfile management
├── configuration.nix                # Root configuration (hardened kernel flags & sysctl)
└── README.md                        # Project specification and deployment guide
```

---

## ⚡ Automated CI/CD Pipeline (`build-hardened-iso.yml`)

The OS is automatically compiled, verified, and packaged using GitHub Actions upon pushing to the `main` branch.

```yaml
name: "Compile SynapseOS Hardened ISO"
on:
  push:
    branches: [ main ]
  release:
    types: [ created ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - name: Checkout Repository
      uses: actions/checkout@v4

    - name: Install Nix
      uses: cachix/install-nix-action@v25
      with:
        nix_path: nixpkgs=channel:nixos-unstable

    - name: Setup Magic Nix Cache
      uses: DeterminateSystems/magic-nix-cache-action@v2

    - name: Compile Hardened Bootable ISO
      run: |
        nix build .#nixosConfigurations.synapseOS.config.system.build.isoImage

    - name: Upload Cryptographic ISO Artifact
      uses: actions/artifacts/upload-artifact@v4
      with:
        name: synapseOS-live-hardened
        path: result/iso/*.iso
```

---

## 🎯 Implementation Roadmap

### Phase 1: Foundational Framework (Current)
* [ ] Initialize the pure NixOS Flake skeleton.
* [ ] Implement the `linux-hardened` kernel profiles and strict sysctl networking rules.
* [ ] Configure GitHub Actions to successfully build and export a standard bootable live ISO.

### Phase 2: AI & Telemetry Integration
* [ ] Package `garak` and its runtime dependencies natively into the system flake.
* [ ] Write custom eBPF packet monitoring hooks to trace inter-process communication during model interaction.
* [ ] Establish the local model caching framework for offline inference (e.g., pulling a quantized 1B/3B parameter SLM into the build).

### Phase 3: Interface & Verification
* [ ] Construct a dedicated Go/Python-based TUI dashboard that launches at boot for rapid network analysis.
* [ ] Implement automated compliance auditing using an open-source security benchmark checker during the compilation phase.
