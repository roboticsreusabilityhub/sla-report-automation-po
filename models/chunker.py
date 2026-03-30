import re
from typing import List, Optional
# class TextChunker:
#     def __init__(self, text):
#         self.text = text

#     def chunk_by_paragraphs(self, min_size=0):
#             """
#             Splits text by double newlines (\n\n). 
#             Optional: min_size can merge tiny snippets into the next paragraph.
#             """
#             # Split by two or more newlines
#             paragraphs = re.split(r'\n\s*\n', self.text)
            
#             chunks = []
#             buffer = ""

#             for p in paragraphs:
#                 p = p.strip()
#                 if not p:
#                     continue
                    
#                 if len(buffer) + len(p) < min_size:
#                     buffer += "\n\n" + p if buffer else p
#                 else:
#                     if buffer:
#                         chunks.append(buffer)
#                     buffer = p
            
#             if buffer:
#                 chunks.append(buffer)
                
#             return chunks
#     def chunk_by_chars(self, chunk_size, overlap=0):
#         """Splits text by a fixed number of characters."""
#         chunks = []
#         start = 0
#         while start < len(self.text):
#             end = start + chunk_size
#             chunks.append(self.text[start:end])
#             start += (chunk_size - overlap)
#         return chunks

#     def chunk_by_words(self, word_count, overlap=0):
#         """Splits text by a fixed number of words."""
#         words = self.text.split()
#         chunks = []
#         start = 0
#         while start < len(words):
#             end = start + word_count
#             chunk = " ".join(words[start:end])
#             chunks.append(chunk)
#             start += (word_count - overlap)
#         return chunks

#     def chunk_recursive(self, max_size, separators=None):
#         """
#         Splits text based on a hierarchy of separators (e.g., \n\n, \n, . )
#         to try and keep paragraphs or sentences together.
#         """
#         if separators is None:
#             separators = ["\n\n", "\n", ". ", " "]
        
#         return self._recursive_split(self.text, separators, max_size)

#     def _recursive_split(self, text, separators, max_size):
#         """Internal helper for recursive splitting logic."""
#         if len(text) <= max_size:
#             return [text]
        
#         # Find the best separator to use
#         current_sep = separators[0]
#         remaining_seps = separators[1:]
        
#         # Split the text
#         splits = text.split(current_sep)
#         final_chunks = []
#         current_chunk = ""

#         for s in splits:
#             # If a single split is still too large, go deeper into separators
#             if len(s) > max_size and remaining_seps:
#                 if current_chunk:
#                     final_chunks.append(current_chunk.strip())
#                     current_chunk = ""
#                 final_chunks.extend(self._recursive_split(s, remaining_seps, max_size))
#             # Build up the current chunk
#             elif len(current_chunk) + len(s) + len(current_sep) <= max_size:
#                 current_chunk += (current_sep if current_chunk else "") + s
#             else:
#                 if current_chunk:
#                     final_chunks.append(current_chunk.strip())
#                 current_chunk = s

#         if current_chunk:
#             final_chunks.append(current_chunk.strip())
            
#         return final_chunks
class Chunker:
    def __init__(self, default_size=5000):
        self.default_size = default_size

# def split_sentences_punctuation(text):
#     """
#     Splits text into sentences using punctuation marks.
    
#     Parameters:
#     text (str): The input text to be split.
    
#     Returns:
#     list: A list of sentences.
#     """
#     # Regular expression to split sentences based on punctuation marks
#     sentences = re.split(r'(?<=[.!?]) +', text)
#     return sentences


# for i, sentence in enumerate(sentences):
#     print(f"Sentence {i+1}:\n{sentence}\n")
    
#     def chunk_recursive(self, max_size, separators=None):
#         """
#         Splits text based on a hierarchy of separators (e.g., \n\n, \n, . )
#         to try and keep paragraphs or sentences together.
#         """
#         if separators is None:
#             separators = ["\n\n", "\n", ". ", " "]
        
#         return self._recursive_split(self.text, separators, max_size)
    
    def chunk_by_size(self, text, size=None):
        """
        Hard-split mechanism. 
        Divides text into exact character-sized blocks.
        """
        size = size or self.default_size
        return [text[i:i + size] for i in range(0, len(text), size)]


    def chunk_by_empty_lines(self, text: str, size: Optional[int] = None) -> List[str]:
        """
        Semantic-split mechanism.
        Splits text by double newlines (\\n\\n) while ensuring no chunk exceeds the size limit.
        If a single paragraph exceeds the size, it is hard-split.

        Parameters
        ----------
        text : str
        size : int, optional

        Returns
        -------
        List[str]
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string.")
        size = size or self.default_size
        if size <= 0:
            raise ValueError("size must be a positive integer.")
        if not text:
            return []

        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_length = 0

        for para in paragraphs:
            # length accounting includes the two newlines we’ll reinsert when joining
            # only if current_chunk already has content
            sep_len = 2 if current_chunk else 0
            para_len = len(para) + sep_len

            if current_length + para_len <= size:
                current_chunk.append(para)
                current_length += para_len
            else:
                # flush current buffer first (if any)
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # if the single paragraph itself is too large, hard-split it
                if len(para) > size:
                    sub_chunks = self.chunk_by_size(para, size=size)
                    chunks.extend(sub_chunks[:-1])
                    # start a new buffer with the last piece
                    last_piece = sub_chunks[-1]
                    current_chunk = [last_piece]
                    current_length = len(last_piece)
                else:
                    current_chunk = [para]
                    current_length = len(para)

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks
