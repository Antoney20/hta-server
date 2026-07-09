from abc import ABC, abstractmethod


class Provider(ABC):
    """
    Adapter for one AI provider. Single responsibility: rendered text in,
    raw text out. Never parses, scores, or touches models.
    """

    def __init__(self, api_key: str, model_string: str, temperature: float, max_tokens: int):
        self.api_key = api_key
        self.model_string = model_string
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def run(self, rendered: str) -> str:
        """Send rendered context, return the model's raw text. Raises ConnectionErr/ProcessingError."""
        raise NotImplementedError