"""Interface placeholder for a future visual active-speaker fallback."""
from abc import ABC, abstractmethod


class ActiveSpeakerBackend(ABC):
    @abstractmethod
    def detect(self, video_path: str) -> list[dict]:
        """Return video-timeline speaking intervals after a future backend is supplied."""
