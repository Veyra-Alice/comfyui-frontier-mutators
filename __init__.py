"""ComfyUI nodes for stochastic exploration near a known-good parameter frontier."""

from .nodes import FrontierFloatMutator, FrontierIntegerMutator


NODE_CLASS_MAPPINGS = {
    "FrontierFloatMutator": FrontierFloatMutator,
    "FrontierIntegerMutator": FrontierIntegerMutator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrontierFloatMutator": "Frontier Mutator (Float)",
    "FrontierIntegerMutator": "Frontier Mutator (Integer)",
}

WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
