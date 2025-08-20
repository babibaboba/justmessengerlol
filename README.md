# JustMessenger

JustMessenger is a modern, hybrid messenger supporting both centralized client-server and decentralized P2P communication. Built with Python and the Kivy framework, it offers a flexible and extensible platform for text, voice, and audio messaging.

## Core Features

-   **Hybrid Architecture**:
    -   **Client-Server**: A classic mode where all messages are routed through a central server.
    -   **P2P (Internet)**: A decentralized mode using a DHT (Kademlia) for peer discovery and STUN for NAT traversal.
    -   **P2P (Local Network)**: For direct communication within a local network without an internet connection.
    -   **P2P (Bluetooth)**: For direct communication between nearby devices using Bluetooth.
-   **Communication**:
    -   **Text Chat**: Real-time, responsive text messaging with a rich emoji panel.
    -   **Voice Calls**: Secure, P2P voice calls powered by **WebRTC (`aiortc`)**, ensuring low latency and high quality.
    -   **Audio Messages**: Record and send local audio messages.
-   **Extensibility**:
    -   **Plugin System**: Easily extend functionality with custom plugins (e.g., file transfers).
-   **Customization & UI**:
    -   **Theming**: Switch between light and dark UI themes, with support for native Windows title bar theming.
    -   **Localization**: Supports multiple languages (English and Russian).
    -   **Responsive UI**: The interface is built to be intuitive and scales with window size.
-   **Security**:
    -   **Encrypted Configuration**: Local settings are encrypted to protect user data.
    -   **Secure P2P Channels**: P2P communication channels are established securely.

## Technologies

-   **Language**: Python 3
-   **GUI**: Kivy
-   **Voice & Audio**:
    -   **WebRTC**: `aiortc` for real-time P2P voice calls.
    -   **Local Audio**: `sounddevice` and `soundfile` for microphone/speaker management and audio message recording.
-   **P2P Networking**:
    -   **DHT**: `kademlia` for peer discovery.
    -   **NAT Traversal**: `pystun3`
-   **Serialization**: `msgpack` for efficient data packing.
-   **Compression**: `zstandard` for compressing network traffic.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <project_folder>
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # Create the environment
    python -m venv venv

    # Activate on Windows
    .\venv\Scripts\activate

    # Activate on macOS / Linux
    source venv/bin/activate
    ```

3.  **Install the required libraries:**
    ```bash
    pip install -r VoiceChat/requirements.txt
    ```
    *Note: Some libraries like `sounddevice` may require system-level dependencies (e.g., `libportaudio2` on Debian/Ubuntu). Please refer to the library's documentation if you encounter issues.*

## Usage

### 1. Server (for Client-Server mode)

To use the "Client-Server" mode, you must first run the server.
```bash
python VoiceChat/server/server.py
```
The server will start on `127.0.0.1:12345`.

### 2. Client

Run the client script:
```bash
python VoiceChat/client/client.py
```
Upon launch, a dialog box will appear, prompting you to choose an operating mode:
-   `Client-Server`
-   `P2P (Internet)`
-   `P2P (Local Network)`
-   `P2P (Bluetooth)`

After selecting a mode and entering a username, the main chat window will open.

## Project Structure

```
.
├── VoiceChat/
│   ├── client/              # Client source code (Kivy)
│   │   ├── client.py
│   │   ├── voicechat.kv
│   │   ├── p2p_manager.py
│   │   └── ...
│   ├── server/              # Server source code
│   │   ├── server.py
│   │   └── ...
│   ├── plugins/             # Directory for plugins
│   │   └── file_transfer/
│   ├── README.md            # This file
│   └── requirements.txt     # Project dependencies
└── ...
