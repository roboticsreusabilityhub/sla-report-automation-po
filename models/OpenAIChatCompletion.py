from typing import List, Optional
from openai import OpenAI
from models.Message import SystemMessage, Message, UserMessage
import time


class OpenAIChatCompletion:
    """
    Simple chat completion wrapper for OpenAI (non-Azure) that mirrors the previous behavior.

    - Maintains a running message history unless `without_history=True`.
    - Accepts a `SystemMessage` on init.
    - Returns the assistant's text content.
    """

    def __init__(
        self,
        api_key: str,
        system_message: SystemMessage,
        organization: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4.1",
        request_timeout: int = 30,
        max_retries: int = 2,
    ):
        """
        Args:
            api_key: OpenAI API key.
            system_message: Your system prompt (models.Message.SystemMessage).
            organization: Optional OpenAI org id (if applicable).
            base_url: Optional custom base URL (rare; mostly for proxies).
            default_model: Default OpenAI model name.
            request_timeout: Timeout in seconds for each request.
            max_retries: Number of simple retries on transient errors.
        """
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=api_key,
            organization=organization,
            base_url=base_url,
            timeout=request_timeout,
        )

        self.default_model = default_model
        self.request_timeout = request_timeout
        self.max_retries = max_retries

        # Store system message and running history
        self.system_message = {"role": "system", "content": system_message.content}
        self.messages: List[dict] = [self.system_message]

    def _request_with_retries(self, *, model: str, messages: List[dict], temperature: float):
        """Basic retry helper for transient failures."""
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                return self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                )
            except Exception as e:
                last_err = e
                # Backoff: 0.5s, 1s, 2s (for max_retries=2)
                time.sleep(0.5 * (2 ** attempt))
        # If here, all attempts failed
        raise last_err

    def get_completion(
        self,
        prompt: Message,
        without_history: bool = True,
        model: str = None,
        temperature: float = 0,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            prompt: A Message (with .role and .content).
            without_history: If True, do not include previous messages in request.
            model: OpenAI public model name. Defaults to self.default_model.
            temperature: Sampling temperature.

        Returns:
            str: Assistant response text.
        """
        model = model or self.default_model

        # Append the new user/assistant tool message to the local history
        self.messages.append({"role": prompt.role, "content": prompt.content})

        if without_history:
            messages = [self.system_message, self.messages[-1]]
        else:
            messages = self.messages

        completion = self._request_with_retries(
            model=model, messages=messages, temperature=temperature
        )

        # Extract assistant text safely
        choice = completion.choices[0]
        content = choice.message.content or ""
        return content
