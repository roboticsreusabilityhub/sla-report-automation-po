
from openai import AzureOpenAI, OpenAI
from models.Message import SystemMessage,Message,UserMessage
class OpenAIChatCompletion :
    def __init__(self,azure_endpoint,api_version,api_key,system_message: SystemMessage):
        self.azure_endpoint= azure_endpoint
        self.api_version= api_version
        self.api_key=api_key
        self.client  = AzureOpenAI(azure_endpoint=azure_endpoint,api_version=api_version,api_key=api_key)

        self.system_message={
            "role":"system",
            "content":system_message.content
        }
        self.messages=[{
            "role":"system",
            "content":system_message.content
        }]






    def get_completion(self,prompt: Message, without_history=False,model="gpt-4o-mini" ,temperature=0.1):

        completion=''
        self.messages.append({
            "role":prompt.role,
            "content": prompt.content
        })

        if without_history:
            messages= [self.system_message,self.messages[len(self.messages)-1]]

            completion = self.client.chat.completions.create(
            model=model,
            messages=messages, 
            temperature=temperature
            )
            
        else:
            completion = self.client.chat.completions.create(
            model=model,
            messages=self.messages, 
            )
        


        return completion.choices[0].message.content

