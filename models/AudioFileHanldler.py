import azure.cognitiveservices.speech as speechsdk
import time
# Note: Since the transcriber returns a ConversationTranscriptionResult, 
# we can rely on it having the speaker_id attribute.

class AudioFileHandler:

    def __init__(self, speech_transcriber): # Renamed for clarity
        """
        Initializes the handler with a ConversationTranscriber object.
        """
        self.speech_recognizer = speech_transcriber # Still using the generic name internally
        self.final_transcript = []
        self.done = False

    # --- Event Handlers ---
    

    # Use 'transcribed' results, not 'recognized'
    def _transcribed_cb(self, evt: speechsdk.transcription.ConversationTranscriptionEventArgs): 
        """Event handler for final, completed transcription results with Speaker ID."""
    
     
        # but Transcriber typically uses ConversationTranscriptionResultType for success)
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            try :
                print("Event Transcribed Speech")
                
                #  FIX 3: Speaker ID is guaranteed with Transcriber, access it directly
                speaker_id = evt.result.speaker_id
                
                text = evt.result.text
                diarized_text = f"{speaker_id}: {text}"
                
                print(f"TRANSCRIBED: {diarized_text}")
                self.final_transcript.append(diarized_text)
    
            except Exception as e: 
                print(f"Error processing transcribed event: {e}")


    def _session_stopped_cb(self, evt: speechsdk.SessionEventArgs):
        """Event handler for when the recognition session ends (e.g., end of file)."""
        print(f"SESSION STOPPED: {evt}")
        self.done = True

    def _canceled_cb(self, evt: speechsdk.SpeechRecognitionCanceledEventArgs):
        """Event handler for cancellation events (errors or explicit stop)."""
        print(f"CANCELED: Reason={evt.result.reason}")
        if evt.result.reason == speechsdk.CancellationReason.Error:
            print(f"CANCELED: ErrorDetails={evt.error_details}")
        self.done = True
        
    # --- Main Recognition Method ---

    def recognize_continuous(self):
        try:
            """
            Performs continuous transcription using ConversationTranscriber.
            """
            self.final_transcript = []
            self.done = False

  
            self.speech_recognizer.transcribed.connect(self._transcribed_cb) 
            self.speech_recognizer.session_stopped.connect(self._session_stopped_cb)
            self.speech_recognizer.canceled.connect(self._canceled_cb)

            print("Starting conversation transcription...")
            
      
            self.speech_recognizer.start_transcribing_async().get() 

            while not self.done:
                time.sleep(0.5)
            
  
            self.speech_recognizer.stop_transcribing_async().get() 
            
            full_transcript = "\n".join(self.final_transcript)
            print("\n--- Conversation Transcription Complete ---")
            
            return full_transcript
        
        except Exception as e:
            print("error:"+e)

