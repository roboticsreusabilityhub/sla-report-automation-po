def chunk_conversation(text: str, max_chars: int = 20000) -> list[str]:
    """
    Splits the conversation text into chunks smaller than max_chars.
    It tries to break only at newline characters to keep speaker turns intact.
    """
    lines = text.split('\n')
    chunks = []
    current_chunk = ""

    for line in lines:
        # Check if adding the next line exceeds the limit
        if len(current_chunk) + len(line) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"

    # Add the final chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
def save_to_file(transcript: str, filename: str = "transcript.txt"):
    """Saves the given string content to a text file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(transcript)
        print(f"✅ Successfully saved transcript to {filename}")
    except IOError as e:
        print(f"❌ Error saving file: {e}")
def read_file(file_path):
    with open(file_path,'r') as file:
        content = file.read()
        return content
    