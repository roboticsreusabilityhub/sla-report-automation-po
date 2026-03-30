class Message: 
    role =""
    content=''

class SystemMessage(Message):
    def __init__(self,content):
        self.role="system"
        self.content=content


    def set(self,content):
        self.content= content



class UserMessage(Message):
    def __init__(self,content):
        self.role="user"
        self.content=content
