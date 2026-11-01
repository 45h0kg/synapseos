{ modules }:
{ hostPkgs, ... }:
let
  huggingFace = path: hash: hostPkgs.fetchurl { url = "https://huggingface.co/${path}"; inherit hash; };

  stories260K = huggingFace "ggml-org/models/resolve/main/tinyllamas/stories260K.gguf" "sha256-Jwy6G9UQn0LQM1D2BAYCRWBGTbFzwOOH2R8EJtO9JW0=";
  stories15Mq4 = huggingFace "ggml-org/models/resolve/main/tinyllamas/stories15M-q4_0.gguf" "sha256-ZpZ/vs5tvpeIZZP9u3NYlYSSfikRnsMfCAkHMtGGFzk=";
  stories15M = huggingFace "karpathy/tinyllamas/resolve/main/stories15M.pt" "sha256-PaAMD+9oTz+DtFdzaDfEarVekqJmYrYdYQTeLScccI0=";

  picklescan = hostPkgs.fetchurl {
    url = "https://files.pythonhosted.org/packages/43/71/3035a2ca54845ab1990635ce4ffb115ddd7ed3529dd5afec4e22846d546e/picklescan-1.0.5-py3-none-any.whl";
    hash = "sha256-Krs9SVmn7pzLHhKW23xW9iS/bTRbk6Cpz0GFvGUNwv0=";
  };

  python = hostPkgs.python3.withPackages (ps: [ ps.torch ]);

  corpus = hostPkgs.runCommand "synapse-bench-corpus" { nativeBuildInputs = [ python ]; } ''
    python3 ${./bench-corpus.py} $out
  '';

  models = hostPkgs.linkFarm "synapse-bench-models" [
    { name = "stories260K.gguf"; path = stories260K; }
    { name = "stories15M-q4_0.gguf"; path = stories15Mq4; }
    { name = "stories15M.pt"; path = stories15M; }
  ];

  wheel = hostPkgs.runCommand "picklescan.whl" { } "cp ${picklescan} $out";
in
{
  name = "synapse-benchmark";
  globalTimeout = 10800;
  nodes.machine = {
    imports = modules;
    synapseos.aiTools.enable = true;
    synapseos.chamber.torch = true;
    synapseos.models."stories260K.gguf" = {
      url = "https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories260K.gguf";
      hash = "sha256-Jwy6G9UQn0LQM1D2BAYCRWBGTbFzwOOH2R8EJtO9JW0=";
    };
    virtualisation.memorySize = 8192;
    virtualisation.cores = 4;
    virtualisation.diskSize = 16384;
    boot.kernel.sysctl."vm.panic_on_oom" = 0;
    environment.systemPackages = [ hostPkgs.curl ];
  };
  testScript = ''
    machine.wait_for_unit("multi-user.target")
    machine.succeed(
        "PYTHONUNBUFFERED=1 ${hostPkgs.python3}/bin/python3 ${./bench-run.py} ${corpus} ${models} ${wheel} "
        "2>&1 | tee /dev/ttyS0 > /tmp/bench.log",
        timeout=12600)
    machine.succeed("grep -q BENCH-DONE /tmp/bench.log")
  '';
}
