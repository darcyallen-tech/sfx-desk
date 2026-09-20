"""First-run / health checks for SFX Desk (no secrets stored here)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SetupStatus:
    torch_ok: bool
    cuda_ok: bool
    sa3_ok: bool
    hf_logged_in: bool
    messages: list[str]

    @property
    def ready_for_sa3(self) -> bool:
        return self.torch_ok and self.cuda_ok and self.sa3_ok and self.hf_logged_in


def check_setup() -> SetupStatus:
    messages: list[str] = []
    torch_ok = False
    cuda_ok = False
    sa3_ok = False
    hf_logged_in = False

    try:
        import torch

        torch_ok = True
        cuda_ok = bool(torch.cuda.is_available())
        if not cuda_ok:
            messages.append("CUDA GPU not detected. SFX Desk needs NVIDIA + CUDA for SA3/MOSS.")
    except Exception:
        messages.append("PyTorch missing. Run scripts\\setup_windows.bat")

    try:
        import stable_audio_3  # noqa: F401

        sa3_ok = True
    except Exception:
        messages.append(
            "stable-audio-3 not installed. Run scripts\\setup_windows.bat"
        )

    try:
        from huggingface_hub import get_token

        tok = get_token()
        hf_logged_in = bool(tok)
        if not hf_logged_in:
            messages.append(
                "Not logged into Hugging Face. Accept the SA3 license, then run "
                "scripts\\hf_login.bat (browser login preferred, or paste your own token)."
            )
    except Exception:
        messages.append("huggingface_hub missing or login check failed.")

    if torch_ok and cuda_ok and sa3_ok and hf_logged_in:
        messages.append("SA3 setup looks good.")

    return SetupStatus(
        torch_ok=torch_ok,
        cuda_ok=cuda_ok,
        sa3_ok=sa3_ok,
        hf_logged_in=hf_logged_in,
        messages=messages,
    )


SA3_LICENSE_URL = "https://huggingface.co/stabilityai/stable-audio-3-small-sfx"
HF_TOKENS_URL = "https://huggingface.co/settings/tokens"
