# Local Command-Generation Model

## Runtime choice

The generation adapter uses `llama-cpp-python` with the Qwen2.5-1.5B-Instruct GGUF model as an offline fallback. Common, well-specified requests use deterministic command templates and do not load the language model. The model is not committed to Git because it is a large third-party binary.

The tested agent host is Ubuntu-based x86-64 Linux with an Intel Core i3-1005G1 (2 physical cores / 4 logical CPUs), about 7.5 GiB RAM, and no supported CUDA accelerator. The selected Q4_K_M quantization is approximately 1.12 GB. The current tuned defaults are a 1,024-token context, 2 CPU threads, `n_batch=128`, `n_ubatch=128`, `n_gpu_layers=0`, and a 48-token output ceiling. The prompt asks for one Bash command only, not a JSON explanation. These settings are configurable and may not be optimal on other CPUs.

## Install the Python runtime

The base dependencies, including the Bash parser, are installed from the locked project environment. NumPy is pinned to 2.2.6 because the serialized intent classifier was built with that exact version and the model loader checks it. The C++ inference binding is installed separately because it may compile native code and is not needed by the classifier or syntax validator:

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

For several requests in one session, reuse the loaded model:

```bash
uv run nl2bash generate --interactive --timings
```

Enter one request per line; type `exit` or `quit` to stop. The classifier and frozen configuration are loaded once. The language model is loaded lazily when the first request misses the deterministic templates, then reused. Per-request timing data separates deterministic-template time or LLM prompt evaluation, token generation, and validation.

The one-shot command loads the classifier and frozen threshold, checks source/configuration hashes, and tries deterministic generation first. Only an LLM fallback performs a model load. The frozen configuration stores the portable model SHA-256. After a successful full hash, a machine-local sidecar named `<model>.nl2bash-integrity.json` records the hash and local file identity. Regular CLI startup checks this sidecar instead of rereading the full 1.1 GB model. On a fresh machine, or after the model file changes, the first request performs a full SHA-256 verification and refreshes the sidecar. The CLI then checks Bash syntax and applies safety heuristics. No generated command is executed.

## Resource and safety notes

- CPU inference is slower than GPU inference. The default 1.5B model is a practical fallback for this 2-core machine, not a claim of production-grade command accuracy.
- The model can misunderstand requests or produce incorrect commands. Unsupported long requests may hit the 48-token output cap and fail closed. Review the request, assumptions, generated command, and warnings before using it.
- The syntax checker uses `bash -n` in parse-only mode and `bashlex` for supplementary AST analysis. It does not execute command text.
- Safety rules are conservative pattern checks. They can miss risky behaviour and can flag legitimate administration tasks. No clean result is a guarantee that a command is safe.
- Inference is local. Model installation/download requires network access, but normal generation does not call a hosted model API.
