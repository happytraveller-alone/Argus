import os


def normalize_extracted_project_root(base_path: str) -> str:
    candidates = [
        item
        for item in os.listdir(base_path)
        if not str(item).startswith("__") and not str(item).startswith(".")
    ]
    if len(candidates) != 1:
        return base_path
    nested = os.path.join(base_path, candidates[0])
    if os.path.isdir(nested):
        return nested
    return base_path
