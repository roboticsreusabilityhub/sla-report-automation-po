from models.Message import SystemMessage, UserMessage
from models.OpenAIChatCompletion import OpenAIChatCompletion
class TextSummarizartionHandler:

    def __init__(self,azure_endpoint,api_version,api_key):
        self._system_prompt=SystemMessage(content="""
        You are an expert in text summarization. Your task is to summarize the given text.

        **Strictly adhere to the following rules:**
        1.  **Summarize Only:** Do not include any extra words, introductions, or explanations outside of the direct translation.
        2.  **Preserve Structure:** The output must maintain the exact line breaks and labels.
        """)
        
        self.openAI_completion_model=OpenAIChatCompletion(azure_endpoint=azure_endpoint,api_version=api_version,api_key=api_key,system_message=self._system_prompt)
        pass

    def summarize_text(self,text):
        user_message=UserMessage(content=text)
        completion=self.openAI_completion_model.get_completion(prompt=user_message,without_history=True)
        return completion
