import pyaudio
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

class AudioManager:
    def __init__(self):
        self.audio = pyaudio.PyAudio()

    def get_audio_devices(self):
        devices = {'input': [], 'output': []}
        for i in range(self.audio.get_device_count()):
            dev_info = self.audio.get_device_info_by_index(i)
            try:
                host_api_info = self.audio.get_host_api_info_by_index(dev_info.get('hostApi'))
                host_api_name = host_api_info.get('name')
            except Exception:
                host_api_name = "Unknown API"

            if dev_info.get('maxInputChannels') > 0:
                devices['input'].append({
                    'index': i,
                    'name': dev_info.get('name'),
                    'hostApiName': host_api_name
                })
            if dev_info.get('maxOutputChannels') > 0:
                devices['output'].append({
                    'index': i,
                    'name': dev_info.get('name'),
                    'hostApiName': host_api_name
                })
        return devices

    def _get_device_interface(self, device_index, data_flow):
        devices = AudioUtilities.GetDevices()
        for dev in devices:
            if dev.id == self.audio.get_device_info_by_index(device_index)['name'] and dev.DataFlow == data_flow:
                 return dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return None

    def get_volume(self, device_index, device_type):
        data_flow = 0 if device_type == 'output' else 1 # 0 for eRender, 1 for eCapture
        try:
            interface = self._get_device_interface(device_index, data_flow)
            if interface:
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                return int(volume.GetMasterVolumeLevelScalar() * 100)
        except Exception as e:
            print(f"Could not get volume for device {device_index}: {e}")
        return 50 # Default value

    def set_volume(self, device_index, device_type, volume_level):
        data_flow = 0 if device_type == 'output' else 1
        try:
            interface = self._get_device_interface(device_index, data_flow)
            if interface:
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(volume_level / 100, None)
        except Exception as e:
            print(f"Could not set volume for device {device_index}: {e}")

    def __del__(self):
        self.audio.terminate()
