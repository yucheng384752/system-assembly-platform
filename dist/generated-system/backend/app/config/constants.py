import os

VALID_MATERIALS: list[str] = [
    item.strip()
    for item in os.environ.get("VALID_MATERIALS_CSV", "").split(",")
    if item.strip()
]
VALID_SLITTING_MACHINES: list[int] = [
    int(item.strip())
    for item in os.environ.get("VALID_SLITTING_MACHINES_CSV", "").split(",")
    if item.strip()
]


def get_material_list() -> list[str]:
    return VALID_MATERIALS


def get_slitting_machine_list() -> list[int]:
    return VALID_SLITTING_MACHINES
