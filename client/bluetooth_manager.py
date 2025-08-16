# -*- coding: utf-8 -*-

import bluetooth
import threading
import queue

class BluetoothManager:
    def __init__(self, username, callback_queue):
        self.username = username
        self.callback_queue = callback_queue
        self.server_sock = None
        self.client_sock = None
        self.running = False
        self.server_thread = None
        self.client_thread = None
        self.uuid = "94f39d29-7d6d-437d-973b-fba39e49d4ee" # Unique UUID for this app

    def start(self):
        self.running = True
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()
        print("BluetoothManager server started.")

    def stop(self):
        self.running = False
        if self.server_sock:
            self.server_sock.close()
        if self.client_sock:
            self.client_sock.close()
        print("BluetoothManager stopped.")

    def discover_devices(self):
        """Scans for nearby Bluetooth devices."""
        print("Scanning for Bluetooth devices...")
        try:
            nearby_devices = bluetooth.discover_devices(duration=8, lookup_names=True, flush_cache=True, lookup_class=False)
            self.callback_queue.put(('bt_devices_discovered', nearby_devices))
            return nearby_devices
        except Exception as e:
            print(f"Error discovering devices: {e}")
            self.callback_queue.put(('bt_discovery_error', str(e)))
            return []

    def run_server(self):
        """Listens for incoming Bluetooth connections."""
        try:
            self.server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.server_sock.bind(("", bluetooth.PORT_ANY))
            self.server_sock.listen(1)

            port = self.server_sock.getsockname()[1]

            bluetooth.advertise_service(self.server_sock, "VoiceChatApp",
                                      service_id=self.uuid,
                                      service_classes=[self.uuid, bluetooth.SERIAL_PORT_CLASS],
                                      profiles=[bluetooth.SERIAL_PORT_PROFILE])
            
            print(f"Waiting for connection on RFCOMM channel {port}")
            
            while self.running:
                try:
                    client_sock, client_info = self.server_sock.accept()
                    self.callback_queue.put(('bt_connection_received', client_info))
                    # Handle the connection in a new thread
                    handler_thread = threading.Thread(target=self.handle_client, args=(client_sock,), daemon=True)
                    handler_thread.start()
                except bluetooth.btcommon.BluetoothError:
                    # This happens when the socket is closed
                    break
        except OSError as e:
            # This specific error (10040 or similar) can happen if the BT adapter is off
            print(f"Bluetooth server OS error: {e}")
            self.callback_queue.put(('bt_adapter_error', 'Please ensure your Bluetooth adapter is turned on.'))
        except Exception as e:
            print(f"Bluetooth server error: {e}")
            self.callback_queue.put(('bt_server_error', str(e)))

    def handle_client(self, sock):
        """Handles an incoming client connection."""
        try:
            while self.running:
                data = sock.recv(1024)
                if not data:
                    break
                message = data.decode('utf-8')
                self.callback_queue.put(('bt_message_received', message))
        except Exception as e:
            print(f"Error handling BT client: {e}")
        finally:
            sock.close()

    def connect_to_device(self, addr):
        """Connects to a specific Bluetooth device."""
        print(f"Connecting to {addr}...")
        try:
            service_matches = bluetooth.find_service(uuid=self.uuid, address=addr)

            if len(service_matches) == 0:
                self.callback_queue.put(('bt_connection_failed', "Service not found."))
                return

            first_match = service_matches[0]
            port = first_match["port"]
            name = first_match["name"]
            host = first_match["host"]

            sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            sock.connect((host, port))
            
            self.client_sock = sock
            self.callback_queue.put(('bt_connection_successful', name))
            
            # Start a thread to listen for messages from this connection
            self.client_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
            self.client_thread.start()

        except Exception as e:
            print(f"Error connecting to device: {e}")
            self.callback_queue.put(('bt_connection_failed', str(e)))

    def listen_for_messages(self):
        """Listens for messages on the client socket."""
        try:
            while self.running and self.client_sock:
                data = self.client_sock.recv(1024)
                if not data:
                    break
                message = data.decode('utf-8')
                self.callback_queue.put(('bt_message_received', message))
        except Exception as e:
            print(f"Error in client listening thread: {e}")
        finally:
            if self.client_sock:
                self.client_sock.close()
                self.client_sock = None
            self.callback_queue.put(('bt_disconnected', None))


    def send_message(self, message):
        """Sends a message to the connected device."""
        if self.client_sock:
            try:
                self.client_sock.send(message.encode('utf-8'))
                return True
            except Exception as e:
                print(f"Error sending BT message: {e}")
                return False
        return False
