"""Content allowlist for the reviewed CMU MotionBuilder BVH clips."""
from pathlib import Path

from engine.assets.registry import file_hash


CMU_TERMS = "https://mocap.cs.cmu.edu/"
CMU_MIRROR = "https://github.com/una-dinosauria/cmu-mocap/blob/09a07f54f3bbb58797325f009282d0b2048a2871"
CLIPS = {
    "55639435a749d1785fdcbf9d3a77fe4b114c3d72824b17562b9e401b9352fa94": ("22_21", "gesture", "022"),
    "91d947f840845d00054dd331cb7e5c6a0195ee56406dc43273dbdc26467bc066": ("35_01", "walk", "035"),
    "d428d2c4fa8873d077537567ad32c95b9687a479a10522d314b203fddea37daf": ("141_16", "gesture", "141"),
    "50480e797770f6ae881caba3f27746a750bbdae237342bb72b2723df9f0663c7": ("141_17", "sit", "141"),
    "1219b0ed7ef155e4c3acbd3e18525bfb926644bc1265482873fef21705aa1808": ("141_19", "walk", "141"),
    "2c2b1e357e0e3636aaa9f510dd3cb3c51e05592a24bd2f8ad6e11d57fb36ee2c": ("141_34", "run", "141"),
}


def reviewed_capture(path: Path):
    if path.suffix.lower() != ".bvh" or path.stat().st_size > 2_000_000:
        raise ValueError("Choose a reviewed BVH source up to 2 MB")
    digest = file_hash(path)
    if digest not in CLIPS:
        raise ValueError("BVH bytes do not match a reviewed CMU capture")
    return digest, CLIPS[digest]
