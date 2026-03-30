import re
from typing import List, Optional



class Chunker:
    def __init__(self, default_size=5000):
        self.default_size = default_size
    
    def chunk_by_size(self, text, size=None):
        """
        Hard-split mechanism. 
        Divides text into exact character-sized blocks.
        """
        size = size or self.default_size
        return [text[i:i + size] for i in range(0, len(text), size)]


    def chunk_recursive(self, text, max_size, separators=None, overlap=1000):
        """
        Splits text based on a hierarchy of separators (e.g., \\n\\n, \\n, '. ', ' ')
        to try and keep paragraphs or sentences together, with an optional character
        overlap between consecutive chunks.

        Args:
            text (str): Input text.
            max_size (int): Maximum characters per chunk (hard cap).
            separators (list[str] | None): Ordered list of separators, most to least coarse.
            overlap (int): Number of characters to overlap between adjacent chunks.
                        Must satisfy 0 <= overlap < max_size.

        Returns:
            list[str]: List of chunks (each length <= max_size).
        """
        if separators is None:
            separators = ["\n\n", "\n", ". ", " "]

        if not isinstance(max_size, int) or max_size <= 0:
            raise ValueError("max_size must be a positive integer.")

        if not isinstance(overlap, int) or overlap < 0:
            raise ValueError("overlap must be a non-negative integer.")
        if overlap >= max_size:
            raise ValueError("overlap must be strictly less than max_size.")

        return self._recursive_split(text, separators, max_size, overlap)


    def _recursive_split(self, text, separators, max_size, overlap):
        """
        Internal helper for recursive splitting logic with overlap.
        """
        if len(text) <= max_size:
            return [text]

        # Choose current separator and remaining ones
        current_sep = separators[0]
        remaining_seps = separators[1:]

        # Split on the current separator
        splits = text.split(current_sep)

        final_chunks = []
        current_chunk = ""

        for s in splits:
            # If a single split is still too large, go deeper into separators
            if len(s) > max_size and remaining_seps:
                # If we have something accumulated, flush it first
                if current_chunk:
                    final_chunks.append(current_chunk.strip())
                    current_chunk = ""

                # Recursively split this large segment
                sub_chunks = self._recursive_split(s, remaining_seps, max_size, overlap)

                # Merge sub_chunks into final_chunks while ensuring overlap between the
                # last chunk already in final_chunks (if any) and the first sub_chunk.
                if not final_chunks:
                    # Nothing before; just extend
                    final_chunks.extend(sub_chunks)
                else:
                    # There are existing chunks; we want overlap between
                    # final_chunks[-1] and sub_chunks[0].
                    # If we want to enforce overlap, prepend overlap from final_chunks[-1]
                    # into the start of sub_chunks[0] without exceeding max_size.
                    if sub_chunks:
                        prev = final_chunks[-1]
                        carry = prev[-overlap:] if overlap > 0 else ""
                        # Rebuild first sub-chunk with carry
                        first = sub_chunks[0]
                        merged = (carry + first)
                        if len(merged) > max_size:
                            # Trim from the left to keep the most recent content
                            merged = merged[-max_size:]
                        sub_chunks[0] = merged
                    final_chunks.extend(sub_chunks)

                continue

            # Compute what would happen if we append this piece with a separator
            if current_chunk:
                candidate = current_chunk + current_sep + s
            else:
                candidate = s

            if len(candidate) <= max_size:
                # Safe to keep accumulating
                current_chunk = candidate
            else:
                # Flush current chunk, then start a new one with overlap
                if current_chunk:
                    final_chunks.append(current_chunk.strip())

                # Start the next chunk including overlap from the previous chunk
                if overlap > 0 and final_chunks:
                    carry = final_chunks[-1][-overlap:]
                else:
                    carry = ""

                # New chunk starts with carry + s (no leading separator)
                new_chunk = carry + s
                if len(new_chunk) > max_size:
                    # If too long, keep the rightmost max_size characters.
                    # This favors keeping s intact as much as possible and
                    # trims the carried overlap if necessary.
                    new_chunk = new_chunk[-max_size:]

                current_chunk = new_chunk

        # Flush any remaining text
        if current_chunk:
            final_chunks.append(current_chunk.strip())

        return final_chunks
    