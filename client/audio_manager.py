import pyaudio
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

class AudioManager:
    def __init__(self):
        self.audio = pyaudio.PyAudio()

    def get_audio_devices(self):
        devices = {'input': [], 'output': []}
        input_count = 1
        output_count = 1
        for i in range(self.audio.get_device_count()):
            dev_info = self.audio.get_device_info_by_index(i)
            
            try:
                host_api_info = self.audio.get_host_api_info_by_index(dev_info.get('hostApi'))
                host_api_name = host_api_info.get('name')
            except Exception:
                host_api_name = "Unknown API"

            if "DirectSound" not in host_api_name:
                continue

            if dev_info.get('maxInputChannels') > 0:
                name = f"Input Device {input_count}"
                devices['input'].append({
                    'index': i,
                    'name': name,
                    'hostApiName': host_api_name
                })
                input_count += 1
            if dev_info.get('maxOutputChannels') > 0:
                name = f"Output Device {output_count}"
                devices['output'].append({
                    'index': i,
                    'name': name,
                    'hostApiName': host_api_name
                })
                output_count += 1
        return devices

    def _get_device_interface(self, device_index, data_flow):
        # This functionality is temporarily disabled to avoid pycaw errors.
        return None

    def get_volume(self, device_index, device_type):
        # This functionality is temporarily disabled. Returning a default value.
        return 50

    def set_volume(self, device_index, device_type, volume_level):
        # This functionality is temporarily disabled.
        pass

    def __del__(self):
        self.audio.terminate()
