import sounddevice as sd
import numpy as np
from aiortc import MediaStreamTrack
import asyncio
from av import AudioFrame

class AudioManager:
    def __init__(self, config_manager, callback_queue):
        self.config_manager = config_manager
        self.callback_queue = callback_queue
        self.input_devices = {}
        self.output_devices = {}
        self.input_gain = 1.0
        self.output_gain = 1.0
        self.refresh_devices()

    def set_volume(self, gain, vol_type):
        """Sets the input or output volume gain."""
        if vol_type == 'input':
            self.input_gain = gain
        elif vol_type == 'output':
            self.output_gain = gain

    def refresh_devices(self):
        devices = sd.query_devices()
        self.input_devices = {dev['name']: i for i, dev in enumerate(devices) if dev['max_input_channels'] > 0}
        self.output_devices = {dev['name']: i for i, dev in enumerate(devices) if dev['max_output_channels'] > 0}

    def get_input_devices(self):
        return list(self.input_devices.keys())

    def get_output_devices(self):
        return list(self.output_devices.keys())

    def set_default_devices(self):
        try:
            default_input_name = sd.query_devices(kind='input')['name']
            default_output_name = sd.query_devices(kind='output')['name']
            self.config_manager.set_config('audio', 'input_device', default_input_name)
            self.config_manager.set_config('audio', 'output_device', default_output_name)
        except Exception as e:
            print(f"Could not set default audio devices: {e}")

class MicrophoneStreamTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, audio_manager, device=None):
        super().__init__()
        self.audio_manager = audio_manager
        self.device = device
        self.stream = None
        self.samplerate = 48000
        self.channels = 1
        self.dtype = 'int16'
        self.blocksize = 960  # 20ms of audio at 48kHz

    async def start_stream(self):
        try:
            loop = asyncio.get_event_loop()
            self.stream = sd.InputStream(
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                device=self.device,
                channels=self.channels,
                dtype=self.dtype,
                callback=lambda indata, frames, time, status: loop.call_soon_threadsafe(self.on_data, indata)
            )
            self.stream.start()
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            self.stream = None

    def on_data(self, indata):
        # Apply input gain
        gain = getattr(self.audio_manager, 'input_gain', 1.0)
        adjusted_data = (indata * gain).astype(np.int16)
        
        frame = AudioFrame.from_ndarray(adjusted_data.T, format='s16', layout='mono')
        frame.sample_rate = self.samplerate
        try:
            self.queue.put_nowait(frame)
        except asyncio.QueueFull:
            # This can happen if the consumer (WebRTC) is slow.
            # It's generally safe to just drop a frame.
            pass

    async def recv(self):
        if not self.stream:
            await self.start_stream()
            if not self.stream:
                # Return a silent frame if stream couldn't be started
                silent_frame = AudioFrame(format='s16', layout='mono', samples=self.blocksize)
                silent_frame.sample_rate = self.samplerate
                return silent_frame
        
        return await self.queue.get()

    async def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        await super().stop()


class AudioTrackPlayer:
    def __init__(self, track, audio_manager, device=None):
        self.track = track
        self.audio_manager = audio_manager
        self.device = device
        self.stream = None
        self.samplerate = 48000
        self.channels = 1
        self.dtype = 'int16'

    def start(self):
        try:
            self.stream = sd.OutputStream(
                samplerate=self.samplerate,
                device=self.device,
                channels=self.channels,
                dtype=self.dtype
            )
            self.stream.start()
            asyncio.ensure_future(self.play())
        except Exception as e:
            print(f"Error starting output stream: {e}")

    async def play(self):
        while True:
            try:
                frame = await self.track.recv()
                
                # Apply output gain
                gain = getattr(self.audio_manager, 'output_gain', 1.0)
                ndarray = frame.to_ndarray(format='s16')
                adjusted_data = (ndarray * gain).astype(np.int16)

                self.stream.write(adjusted_data.T)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error playing audio: {e}")
                break

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None