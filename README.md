# JustMessenger

JustMessenger is a hybrid messenger that supports both a centralized client-server architecture and decentralized P2P communication. The application provides text chat and voice call functionality.

## Core Features

-   **Hybrid Architecture**:
    -   **Client-Server**: A classic mode where all messages are routed through a central server.
    -   **P2P (Internet)**: A decentralized mode that uses a DHT (Kademlia) for peer discovery and STUN for NAT traversal, allowing users to communicate directly.
    -   **P2P (Local Network)**: A mode for communication within a single local network without needing an internet connection.
-   **Text Chat**: Real-time text messaging.
-   **Voice Calls**: P2P calls using PyAudio and UDP Hole Punching for a direct connection.
-   **Peer Discovery**: In P2P (Internet) mode, a Kademlia-based DHT is used to find and connect to other users.
-   **Plugins**: Support for plugins to extend functionality.
-   **Customization**: Ability to switch between light and dark UI themes.

## Technologies

-   **Language**: Python 3
-   **GUI**: PyQt6
-   **Audio**: PyAudio
-   **P2P Network**:
    -   **DHT**: `kademlia`
    -   **NAT Traversal**: `pystun3`

## Installation

Follow these steps to set up the project:

1.  **Clone the repository and navigate into the directory:**
    ```bash
    git clone <repository_url>
    cd <project_folder>
    ```

2.  **Create a virtual environment:**
    *This will create a `venv` folder in the project root to store dependencies.*
    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**
    ```bash
    # Windows (Command Prompt or PowerShell)
    .\venv\Scripts\activate

    # macOS / Linux (Bash)
    source venv/bin/activate
    ```
    *After activation, you will see `(venv)` at the beginning of your terminal prompt.*

4.  **Install the required libraries:**
    ```bash
    pip install -r VoiceChat/requirements.txt
    ```
    *Note: Installing `PyAudio` may require additional system dependencies. Please refer to the [PortAudio documentation](http://www.portaudio.com/docs/v19-doxydocs/tutorial_start.html) for details.*

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
Upon launch, a dialog box will appear, prompting you to choose one of three operating modes:
-   `Client-Server`
-   `P2P (Internet)`
-   `P2P (Local Network)`

After selecting a mode and entering a username, the main chat window will open.

## Project Structure

```
.
├── VoiceChat/
│   ├── client/         # Client source code
│   │   ├── client.py
│   │   ├── p2p_manager.py
│   │   └── ...
│   ├── server/         # Server source code
│   │   ├── server.py
│   │   └── ...
│   ├── plugins/        # Directory for plugins
│   │   └── example_plugin/
│   ├── README.md       # This file
│   └── requirements.txt # Project dependencies
└── ...
