from dataclasses import dataclass


@dataclass
class Task:
    id: str
    size: float
    priority: int
    dataSize: float = 0
    memory: float = 0
    service: str = "default"
    status: str = "new"
    location: str = "none"
    transferStartTime: float = 0.0
    transferTime: float = 0.0
    communicationDelay: float = 0.0
    transferCompletionTime: float = 0.0
