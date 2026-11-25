"""MPFB facial control vocabulary reused by host preflight and Blender."""
MOUTH = {"A": "viseme_PP", "B": "viseme_E", "C": "viseme_I", "D": "viseme_aa",
         "E": "viseme_O", "F": "viseme_U", "G": "viseme_FF", "H": "viseme_nn"}
HUMAN_KEYS = set(MOUTH.values()) | {"eyeBlinkLeft", "eyeBlinkRight", "browInnerUp", "jawOpen"}
