"""Official model-file identities at revision 749d1c1a46eb10492095d68fbcf55691ccf137cd.

LFS files use SHA256; small Git blobs use Git's framed SHA1 object identity.
Recorded from the official Hugging Face revision API, never inferred from filenames.
"""
import hashlib
from pathlib import Path

MODEL_FILES = {
    "ve.safetensors": (5695784, "sha256", "f0921cab452fa278bc25cd23ffd59d36f816d7dc5181dd1bef9751a7fb61f63c"),
    "t3_turbo_v1.safetensors": (1915480052, "sha256", "fcf1f8c1d651bb7e3acd69ee5be269b4ac10c02980b7708213d598bc9f7cdf87"),
    "s3gen_meanflow.safetensors": (1064875036, "sha256", "d65cb687a2ed581ee6cc297e919ffefa63386944f42364ae13b78a594945514f"),
    "conds.pt": (169454, "sha256", "b1852099306fd6a7814eb9d0bd10186caba7249596cc23868f78a0eefbfa5033"),
    "added_tokens.json": (418, "git-sha1", "fd85325cdfafc690469b6f0e8aeb5cf4649c1450"),
    "merges.txt": (456318, "git-sha1", "226b0752cac7789c48f0cb3ec53eda48b7be36cc"),
    "special_tokens_map.json": (470, "git-sha1", "b2d2dbc845800c78fe98656af927d831ab4ff7b7"),
    "tokenizer_config.json": (3878, "git-sha1", "58bc759ea7dab3dd5442f0500e493f170eeba67f"),
    "vocab.json": (999186, "git-sha1", "a15dd0028acd1dd2c1c2394c80e1de8f3f12a0e4"),
}


def verify_model_files(directory: Path, identities=None) -> None:
    for name, (size, algorithm, expected) in (identities or MODEL_FILES).items():
        path = directory / name
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError(f"Model file missing or wrong size: {name}; restore the pinned model download")
        digest = hashlib.sha256() if algorithm == "sha256" else hashlib.sha1()
        if algorithm == "git-sha1":
            digest.update(f"blob {size}\0".encode())
        with path.open("rb") as handle:
            while chunk := handle.read(4 * 1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"Model file hash mismatch: {name}; restore the pinned model download")
