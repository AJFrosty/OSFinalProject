from dataclasses import dataclass


@dataclass
class Task:
    id: str
    size: float
    priority: int
    dataSize: float = 0
    memory: float = 8.0
    service: str = "analytics"
    status: str = "new"
    location: str = "none"
    transferStartTime: float = 0.0
    transferTime: float = 0.0
    communicationDelay: float = 0.0
    transferCompletionTime: float = 0.0
    cacheLoadDelay: float = 0.0
    memoryNode: str = "none"
    uploadServer: object = None
