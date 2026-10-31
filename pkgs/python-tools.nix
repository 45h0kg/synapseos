# Generated from PyPI metadata. Sources are pinned by the SHA-256 PyPI publishes.
# Dependencies that nixpkgs already provides come from python3Packages.
{ fetchurl, python3Packages }:

let
  py = python3Packages;

  # Upstream pins are tighter than nixpkgs, so runtime dependency checks are off
  # and the ai-tools check in flake.nix runs the real entry points instead.
  wheel =
    { pname, version, url, hash, dependencies ? [ ] }:
    py.buildPythonPackage {
      inherit pname version dependencies;
      format = "wheel";
      src = fetchurl { inherit url hash; };
      dontCheckRuntimeDeps = true;
      # Dependencies propagate ninja's setup hook, and a wheel has nothing to build.
      dontUseNinjaBuild = true;
      dontUseNinjaInstall = true;
      dontUseNinjaCheck = true;
    };

  sdist =
    { pname, version, url, hash, dependencies ? [ ] }:
    py.buildPythonPackage {
      inherit pname version dependencies;
      pyproject = true;
      build-system = [ py.setuptools ];
      src = fetchurl { inherit url hash; };
      dontCheckRuntimeDeps = true;
      doCheck = false;
    };

  mikeshardmind_base2048 = wheel {
    pname = "mikeshardmind-base2048";
    version = "1.0.4";
    url = "https://files.pythonhosted.org/packages/55/a8/5a6136586daa858063e6c33c58eef3cb0b91e334c8f0815192fd4e4df767/mikeshardmind_base2048-1.0.4-py3-none-any.whl";
    hash = "sha256-Cw5uONLqKuoYcSjDnTAWcytc5Yh1DDxvwp/fh9FDcUc=";
    dependencies = [

    ];
  };

  zalgolib = wheel {
    pname = "zalgolib";
    version = "0.2.2";
    url = "https://files.pythonhosted.org/packages/0a/b7/b2c350a80a69af35e42cab730268280244f87f2f07e3267b88c4f45037de/zalgolib-0.2.2-py3-none-any.whl";
    hash = "sha256-Kura9lLNn4FnQYJpySPXaYgXYuEjxKlHeyLzrJX1X/w=";
    dependencies = [

    ];
  };

  ecoji = sdist {
    pname = "ecoji";
    version = "0.1.1";
    url = "https://files.pythonhosted.org/packages/0b/4c/7e8697513111443cb755023ad7a1d921dc51130be33a63c986d6e2c8fb18/ecoji-0.1.1.tar.gz";
    hash = "sha256-lmWyVF1z6gtODJiXzGV134rn3DlGqCrJ1i2y8UcTmpw=";
    dependencies = [

    ];
  };

  lorem = wheel {
    pname = "lorem";
    version = "0.1.1";
    url = "https://files.pythonhosted.org/packages/90/7e/963834e2a400cefdf72af1e10a106c9e849cb4c149cc7b394cb1492effec/lorem-0.1.1-py3-none-any.whl";
    hash = "sha256-ycKRS1p3ICJBfDmL10t7vXEuc/8Cm6gnIIVeRY8TrkI=";
    dependencies = [

    ];
  };

  garak = wheel {
    pname = "garak";
    version = "0.17.1";
    url = "https://files.pythonhosted.org/packages/7d/03/3c9fac131b956698cc5cffa542c9bbb1ebbb90f03105fd616216f49e1df2/garak-0.17.1-py3-none-any.whl";
    hash = "sha256-zveKeSkec+kOf4lSLzY+yTRL+x4O3mg2LXojebpc/ag=";
    dependencies = [
      mikeshardmind_base2048
      py.transformers
      py.datasets
      py.colorama
      py.tqdm
      py.cohere
      py.anthropic
      py.openai
      py.replicate
      py.google-api-python-client
      py.backoff
      py.nltk
      py.accelerate
      py.avidtools
      py.stdlibs
      py.langchain
      py.cmd2
      py.torch
      py.sentencepiece
      py.markdown
      py.numpy
      zalgolib
      ecoji
      py.deepl
      py.litellm
      py.llm
      py.jsonpath-ng
      py.huggingface-hub
      py.python-magic
      lorem
      py.xdg-base-dirs
      py.wn
      py.ollama
      py.google-cloud-translate
      py.grpcio-tools
      py.langdetect
      py.tiktoken
      py.mistralai
      py.pillow
      py.ftfy
      py.websockets
      py.boto3
      py.py-markdown-table
    ];
  };

  nest_asyncio2 = wheel {
    pname = "nest-asyncio2";
    version = "1.7.4";
    url = "https://files.pythonhosted.org/packages/09/ed/559d2915dce85794bc0c36064043da170da50cd98746dcbddd85d5932017/nest_asyncio2-1.7.4-py3-none-any.whl";
    hash = "sha256-hud7UsPRSWspSvPJRLRCE7m4KhKl7lkMCsxMpGku9sc=";
    dependencies = [

    ];
  };

  zipfile_zstd = wheel {
    pname = "zipfile-zstd";
    version = "0.0.4";
    url = "https://files.pythonhosted.org/packages/b1/3a/bc3011d26bbb490741f58c28a2df559445c59e8524cbbb71ecf33db23bb7/zipfile_zstd-0.0.4-py3-none-any.whl";
    hash = "sha256-yOB741dlwHLrexvnFcieyySKESewFOEqm4rH2yYAwWY=";
    dependencies = [
      py.zstandard
    ];
  };

  inspect_ai = wheel {
    pname = "inspect-ai";
    version = "0.3.286";
    url = "https://files.pythonhosted.org/packages/6d/01/bb308a114fa0dec02a0d9d07075cc1eb16c1d7d35c4359dfa230747bcb0f/inspect_ai-0.3.286-py3-none-any.whl";
    hash = "sha256-8Rwq/thAJlB9kCu8xo56julegHB4a6KRTIgHYel6Ig8=";
    dependencies = [
      py.agent-client-protocol
      py.aiobotocore
      py.anyio
      py.beautifulsoup4
      py.boto3
      py.click
      py.debugpy
      py.docstring-parser
      py.fastapi
      py.fsspec
      py.httpx
      py.ijson
      py.jsonlines
      py.jsonpatch
      py.jsonpath-ng
      py.jsonref
      py.jsonschema
      py.markdown-it-py
      py.mmh3
      nest_asyncio2
      py.numpy
      py.platformdirs
      py.psutil
      py.pydantic
      py.python-dotenv
      py.pyyaml
      py.rich
      py.s3fs
      py.semver
      py.shortuuid
      py.sniffio
      py.tenacity
      py.textual
      py.tiktoken
      py.typing-extensions
      py.universal-pathlib
      py.uvicorn
      zipfile_zstd
      py.zipp
      py.zstandard
    ];
  };
in
{
  inherit garak inspect_ai;
}
