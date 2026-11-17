# Local Command-Generation Model

## Runtime choice

The generation adapter uses `llama-cpp-python` with the Qwen2.5-1.5B-Instruct GGUF model. This is a local CPU inference path and makes no outbound inference API calls. The model is not committed to Git because it is a large third-party binary.

The target agent host was inspected on 2026-11-17: Ubuntu-based x86-64 Linux, 4 logical CPU cores, about 7.5 GiB RAM, and no detected NVIDIA GPU. The selected Q4_K_M quantization is approximately 1.12 GB. The default inference context is 4,096 tokens and the default thread count is capped at four.

## Install the Python runtime

The base dependencies, including the Bash parser, are installed from the locked project environment. The C++ inference binding is installed separately because it may compile native code and is not needed by the classifier or syntax validator:

```bash
uv sync --locked
uv pip install --python .venv/bin/python llama-cpp-python==0.3.37
```

`llama-cpp-python` may compile `llama.cpp` locally. A C++ compiler, CMake, Python development headers, and a working build toolchain are required. On Debian/Ubuntu, the usual build prerequisites are `build-essential`, `cmake`, and `python3-dev`.

## Download the model

Model source: [Qwen2.5-1.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF), Apache-2.0 license. The initial model revision used by this project is `91cad51170dc346986eccefdc2dd33a9da36ead9`.

```bash
mkdir -p "$HOME/.cache/nl2bash/models"
curl -fL --retry 4 \
  'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf' \
  -o "$HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
sha256sum "$HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
```

The downloaded file was verified on the agent host with SHA-256 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`. Verify this checksum after download; do not use a partial or mismatched file.

The expected default model path is:

`~/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf`

Override it with `NL2BASH_LLM_MODEL=/absolute/path/to/model.gguf` or pass `--llm-model` to `nl2bash generate`.

## Run the application

```bash
uv run nl2bash generate \
  --request 'Find all Python files larger than 10 MB in the current directory.'
```

For machine-readable output:

```bash
uv run nl2bash generate --request 'List listening TCP ports.' --json
```

The default command loads the checksum-verified intent classifier and the development-frozen confidence threshold before it loads the local language model. It then extracts entities, generates one command, checks Bash syntax, and applies safety heuristics. No generated command is executed.

## Resource and safety notes

- CPU inference is slower than GPU inference. The default 1.5B model is a practical small-model choice, not a claim of production-grade command accuracy.
- The model can misunderstand requests or produce incorrect commands. Review the request, assumptions, generated command, and warnings before using it.
- The syntax checker uses `bash -n` in parse-only mode and `bashlex` for supplementary AST analysis. It does not execute command text.
- Safety rules are conservative pattern checks. They can miss risky behaviour and can flag legitimate administration tasks. No clean result is a guarantee that a command is safe.
- Inference is local. Model installation/download requires network access, but normal generation does not call a hosted model API.
