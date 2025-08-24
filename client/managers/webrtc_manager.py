import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from .audio_manager import MicrophoneStreamTrack, AudioTrackPlayer

class WebRTCManager:
    def __init__(self, p2p_manager, audio_manager, callback_queue):
        self.p2p_manager = p2p_manager
        self.audio_manager = audio_manager
        self.callback_queue = callback_queue
        self.pcs = {}  # peer_id -> RTCPeerConnection
        self.players = {} # peer_id -> AudioTrackPlayer
        self.relay = MediaRelay()

    async def create_offer(self, peer_id):
        pc = RTCPeerConnection()
        self.pcs[peer_id] = pc

        mic_track = MicrophoneStreamTrack(self.audio_manager, device=self.audio_manager.config_manager.get_config('audio', 'input_device'))
        pc.addTrack(self.relay.subscribe(mic_track))

        @pc.on("track")
        async def on_track(track):
            print(f"Track {track.kind} received from {peer_id}")
            player = AudioTrackPlayer(track, self.audio_manager, device=self.audio_manager.config_manager.get_config('audio', 'output_device'))
            self.players[peer_id] = player
            player.start()
            self.callback_queue.put(('webrtc_track_received', {'peer_id': peer_id, 'kind': track.kind}))

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state for {peer_id} is {pc.connectionState}")
            if pc.connectionState == "failed":
                await self.cleanup_peer(peer_id)

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def handle_offer(self, peer_id, offer_data):
        pc = RTCPeerConnection()
        self.pcs[peer_id] = pc

        mic_track = MicrophoneStreamTrack(self.audio_manager, device=self.audio_manager.config_manager.get_config('audio', 'input_device'))
        pc.addTrack(self.relay.subscribe(mic_track))

        @pc.on("track")
        async def on_track(track):
            print(f"Track {track.kind} received from {peer_id}")
            player = AudioTrackPlayer(track, self.audio_manager, device=self.audio_manager.config_manager.get_config('audio', 'output_device'))
            self.players[peer_id] = player
            player.start()
            self.callback_queue.put(('webrtc_track_received', {'peer_id': peer_id, 'kind': track.kind}))


        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state for {peer_id} is {pc.connectionState}")
            if pc.connectionState == "failed":
                await self.cleanup_peer(peer_id)
        
        offer = RTCSessionDescription(sdp=offer_data["sdp"], type=offer_data["type"])
        await pc.setRemoteDescription(offer)
        
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def handle_answer(self, peer_id, answer_data):
        pc = self.pcs.get(peer_id)
        if pc:
            answer = RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
            await pc.setRemoteDescription(answer)

    async def cleanup_peer(self, peer_id):
        pc = self.pcs.pop(peer_id, None)
        if pc and pc.connectionState != "closed":
            await pc.close()

        player = self.players.pop(peer_id, None)
        if player:
            player.stop()
        
        self.callback_queue.put(('webrtc_connection_closed', peer_id))

    async def close_all_connections(self):
        for peer_id in list(self.pcs.keys()):
            await self.cleanup_peer(peer_id)