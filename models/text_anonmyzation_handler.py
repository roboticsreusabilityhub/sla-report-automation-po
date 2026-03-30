from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from collections import defaultdict
class TextAnonmizationHandler:
    def __init__(self,language_endpoint,language_key):
        self.text_analytics_client= TextAnalyticsClient(endpoint=language_endpoint,credential=AzureKeyCredential(language_key))
        self.placeholder_to_entityName_map={}
        self.target_categories=[
            "Person", "Organization", "Email", "PhoneNumber", # Your current list
            "Address", "IPAddress", "URL",                    # Digital/Physical location
            "CreditCardNumber", "IBAN",                       # Financial
            "USSocialSecurityNumber", "PassportNumber"        # Gov Identity
        ]
        pass

    def anonmyze_text_masked_redaction(self, text: str,language="en"):
            # We wrap the text in a list because the API expects a batch
            response = self.text_analytics_client.recognize_pii_entities(documents=[text],language=language,categories_filter=self.target_categories)
        
            
            # Extract the first (and only) result
            result = [doc for doc in response if not doc.is_error]
            
            if not result:
                return text

            # .redacted_text provides the entity-masked version automatically
            return result[0].redacted_text
    




    def anonmyze_text_entity_redaction(self, text: str,language="en"):


        target_categories = ["Organization", "Email", "Person", "PhoneNumber"]
        response = self.text_analytics_client.recognize_pii_entities([text],language=language,categories_filter=self.target_categories)
        docs = [doc for doc in response if not doc.is_error]
        
        if not docs:
            return text

        doc = docs[0]
        # map_store: keeps track of "Original Name" -> "[CategoryN]"
        # counters: keeps track of how many of each category we've seen
        self.entity_name_to_placeholder_map = {}
        counters = defaultdict(int)

        # Sort entities by offset descending so we don't break string indices
        entities = sorted(doc.entities, key=lambda x: x.offset, reverse=True)
        
        redacted_text = text

        for entity in entities:
            original_val = text[entity.offset : entity.offset + entity.length]
            category = entity.category

            # If we haven't seen this specific name/number before, give it a new ID
            if original_val not in self.entity_name_to_placeholder_map:
                counters[category] += 1
                self.entity_name_to_placeholder_map[original_val] = f"[{category}{counters[category]}]"

            # Perform the replacement
            label = self.entity_name_to_placeholder_map[original_val]
            redacted_text = (
                redacted_text[:entity.offset] + 
                label + 
                redacted_text[entity.offset + entity.length:]
            )
        self._assign_reverse_map(map_store=self.entity_name_to_placeholder_map)

        return redacted_text
    
    def deanonmyize_text(self, text: str):
        original_text = text
        # We sort keys by length longest-to-shortest to avoid partial matches
        for label, original_value in sorted(self.placeholder_to_entityName_map.items(), key=lambda x: len(x[0]), reverse=True):
            original_text = original_text.replace(label, original_value)
        return original_text

    def getEntityNameFromAnonmyzedValue(self,anonmyzed_value:str):
        return self.placeholder_to_entityName_map[anonmyzed_value]

    def _assign_reverse_map(self,map_store):

        for key,value in map_store.items():
            self.placeholder_to_entityName_map[value]=key
