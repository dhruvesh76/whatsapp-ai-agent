from dataclasses import dataclass, field
from enum import Enum


class Status(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass
class UserState:
    status: Status = Status.ACTIVE
    history: list[dict] = field(default_factory=list)
    complaint_count: int = 0


_states: dict[str, UserState] = {}


def get_state(wa_id: str) -> UserState:
    if wa_id not in _states:
        _states[wa_id] = UserState()
    return _states[wa_id]


def reset_conversation(wa_id: str):
    state = get_state(wa_id)
    state.history = []
    state.status = Status.ACTIVE
