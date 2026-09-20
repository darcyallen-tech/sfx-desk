# Changelog

## 1.1.3

- Persist generation elapsed time on each library clip (`gen_elapsed`); library rows show ` - in 1.2s` / `in 12s` / `in 5m 51s` when known (older clips omit the suffix)
- Status + library share the same elapsed formatter (<10s one decimal; 10–59s whole seconds; ≥60s minutes)
- Fix MOSS prompt article: use a/an from the intensity phrase that follows (no more `an punchy…` when type is vowel-initial)

## 1.1.2

- **Fix hard crash (0xC0000005)** on MOSS GGUF Generate: unload SA3/MOSS and clear CUDA on the UI thread before the GGUF worker; never call torch.cuda / empty CUDA cache from the GGUF worker while moss-tts-server owns the GPU
- After GGUF when Keep is off: stop moss-tts-server only (no torch CUDA from the worker)
- **Lazy load:** models / moss-tts-server still start only on first Generate; stop GGUF server on app close so the next launch does not look pre-loaded (VRAM probe at startup is unchanged)

## 1.1.1

- Harden MOSS GGUF: free SA3/MOSS VRAM before gen, single-flight lock, stderr log, one automatic restart/retry on connection reset
- Default GGUF steps 12 (faster/safer); clearer mid-decode crash errors

## 1.1.0

- Optional **MOSS GGUF (SLOWER)** engine (~12 GB VRAM) via openmoss `moss-tts-server`
- Status line shows generation elapsed time (e.g. `in 870 ms`)

## 1.0.0

First public release of **SFX Desk** — always-on-top local SFX companion for DaVinci Resolve.

- Local NVIDIA CUDA generation (Windows)
- **SA3 Small-SFX** daily driver; optional **MOSS v2** when VRAM allows
- Prompt builder: type / texture / space / mic / speed / power + extra + resizable prompt box
- Library with favorites, multi-select, Play / Del
- **Send** straight into Resolve Media Pool bin `SFX Desk` (bin only, free Resolve OK)
- Skinny + always-on-top modes, remembered prefs
- Quiet GitHub Releases update check (status click opens the release page)
- MIT license; bring your own Hugging Face account / model licenses
