"""Cell-day states (PREREGISTRATION.md, section 3.2) and the static water mask (section 3.1)."""
from __future__ import annotations

import numpy as np

from .firemask import CLEAR, CLOUD, FIRE

# Cell-day codes. W (static water) is kept so cell indices stay aligned, but it is left out of every denominator.
N_, U_, T_, F_, W_ = 0, 1, 2, 3, 4
LETTERS = np.array(list("NUTFW"))


def combine(sensors: list[np.ndarray], k: int = 1, firms_fire: np.ndarray | None = None,
            water: np.ndarray | None = None) -> np.ndarray:
    """Per-sensor state arrays (sensors without data are left out) to cell-day codes.

    F: any sensor fire, or a FIRMS fire point in the cell. T: not F, at least k sensors clear.
    U: not F, no sensor clear, at least one sensor cloud. N: everything else.
    W: a static water cell, unless fire was seen there (fire evidence wins).
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if not sensors:
        raise ValueError("no sensor data")
    stack = np.stack(sensors)
    fire = (stack == FIRE).any(0)
    if firms_fire is not None:
        fire = fire | firms_fire
    n_clear = (stack == CLEAR).sum(0)
    cloud = (stack == CLOUD).any(0)
    out = np.full(stack.shape[1:], N_, np.uint8)
    out[(n_clear == 0) & cloud] = U_
    out[n_clear >= k] = T_
    if water is not None:
        out[water] = W_
    out[fire] = F_
    return out


def counts(cells: np.ndarray) -> dict[str, int]:
    """Counts of F, T, U, N, plus W (static water), which stays out of every denominator."""
    return {"F": int((cells == F_).sum()), "T": int((cells == T_).sum()), "U": int((cells == U_).sum()),
            "N": int((cells == N_).sum()), "W": int((cells == W_).sum())}


def blind_share(c: dict[str, int]) -> float | None:
    """U / (T + U), or None when nothing was seen."""
    d = c["T"] + c["U"]
    return c["U"] / d if d else None


def letters(cells: np.ndarray) -> str:
    return "".join(LETTERS[cells].tolist())


class WaterMask:
    """Static water mask: a cell is water if, over the reference days, FireMask said water (3) at least as often as
    clear land (5), and said water at least once. It is built from a period that is not pre-registered."""

    def __init__(self, shape):
        self.n3 = np.zeros(shape, np.int32)
        self.n5 = np.zeros(shape, np.int32)
        self.days = 0

    def add(self, firemask: np.ndarray) -> None:
        self.n3 += firemask == 3
        self.n5 += firemask == 5
        self.days += 1

    def mask(self) -> np.ndarray:
        return (self.n3 > 0) & (self.n3 >= self.n5)
