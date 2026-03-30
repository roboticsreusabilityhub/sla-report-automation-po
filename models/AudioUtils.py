from pydub import AudioSegment

class AudioUtils:
    @staticmethod
    def convert_mp3_to_wav(mp3_path, wav_path):
        """
        Converts an MP3 file to WAV format with PCM encoding (16-bit, 16kHz).
        
        Parameters:
        mp3_path (str): Path to the input MP3 file.
        wav_path (str): Path to save the output WAV file.
        """
        audio = AudioSegment.from_mp3(mp3_path)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)  # 16kHz, mono, 16-bit
        audio.export(wav_path, format="wav", codec="pcm_s16le")