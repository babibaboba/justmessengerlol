import pyaudio
import wave
import threading
import os
import uuid

class AudioRecorder:
    def __init__(self, input_device_index=None):
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 44100  # Use a standard rate for audio
        self.input_device_index = input_device_index

        self.frames = []
        self.is_recording = False
        self.filepath = None
        self._thread = None
        self._audio = pyaudio.PyAudio()
        self._stream = None

    def _recording_thread(self):
        self._stream = self._audio.open(format=self.format,
                                        channels=self.channels,
                                        rate=self.rate,
                                        input=True,
                                        frames_per_buffer=self.chunk,
                                        input_device_index=self.input_device_index)
        self.frames = []
        while self.is_recording:
            try:
                data = self._stream.read(self.chunk, exception_on_overflow=False)
                self.frames.append(data)
            except IOError:
                # Can happen if the device is disconnected
                break

        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        
        self._save_to_file()

    def start(self):
        if self.is_recording:
            return
        self.is_recording = True
        self._thread = threading.Thread(target=self._recording_thread, daemon=True)
        self._thread.start()

    def stop(self):
        if not self.is_recording:
            return None
        self.is_recording = False
        if self._thread:
            self._thread.join() # Wait for the thread to finish
        return self.filepath

    def _save_to_file(self):
        temp_dir = os.path.join(os.getcwd(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"audio_{uuid.uuid4()}.wav"
        self.filepath = os.path.join(temp_dir, filename)

        wf = wave.open(self.filepath, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self._audio.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()

    def __del__(self):
        if self._audio:
            self._audio.terminate()